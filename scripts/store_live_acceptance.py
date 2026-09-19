"""Opt-in Store inspection/search; never approves installation or purchase."""
import asyncio
import json
from pathlib import Path
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from olive.application.service_container import ServiceContainer
from olive.agent.confirmation_service import ConfirmationResponse


async def main():
    query = sys.argv[sys.argv.index("--query") + 1] if "--query" in sys.argv else "Spotify"
    with tempfile.TemporaryDirectory(prefix="olive-store-acceptance-") as directory:
        async def approve(request):
            return ConfirmationResponse(request.tool_name in {"system.open_application", "desktop.inspect_application",
                "desktop.control_application", "desktop.keyboard_input", "application.search"})
        services = ServiceContainer(lambda *args: None, approve, data_dir=directory, migrate=False)
        try:
            desktop = services.desktop
            desktop.configure({"enabled": True, "keyboard_policy": "ask"})
            await desktop.discover_applications()
            app = desktop.discovery.resolve("Microsoft Store")
            result = await desktop.open_application(app.id)
            if not result["verified"]:
                raise RuntimeError("Store launch could not be verified")
            if "--search" in sys.argv:
                from olive.desktop.workflow import DesktopStep
                session = desktop.sessions.sessions[desktop.sessions.current]
                step = DesktopStep(session.identity.id, "search", {"name": "Search", "control_type": "Edit"},
                                   {"text": query}, {"name": query}, "application.search")
                permit = await desktop.gateway.authorize(session, step)
                await desktop.gateway.execute(session, step, permit, desktop.stop_event)
                for _ in range(30):
                    observation = await desktop.gateway.observe(session)
                    session.observe(observation)
                    matches = [c for c in observation["controls"] if c["name"].startswith(query) and "invoke" in c.get("actions", [])]
                    if len(matches) == 1:
                        target = matches[0]
                        search_evidence = target["name"]
                        step = DesktopStep(session.identity.id, "invoke", {"runtime_id": target["runtime_id"]}, {}, {"name": query}, "desktop.control_application")
                        permit = await desktop.gateway.authorize(session, step)
                        await desktop.gateway.execute(session, step, permit, desktop.stop_event)
                        for _ in range(30):
                            desktop.observation = await desktop.gateway.observe(session)
                            if any(c["automation_id"] in {"AcquireNewProduct", "OpenInstalledProduct"} for c in desktop.observation["controls"]):
                                break
                            await asyncio.sleep(.2)
                        break
                    await asyncio.sleep(.2)
                else:
                    raise RuntimeError("Store search did not expose one exact Spotify result")
                if "--preview" in sys.argv:
                    from olive.desktop.action_preview import ActionPreview
                    import re
                    controls = desktop.observation["controls"]
                    def one(identifier):
                        values = [c for c in controls if c["automation_id"] == identifier]
                        if len(values) != 1:
                            raise ValueError("Store metadata is unavailable or ambiguous: " + identifier)
                        return values[0]
                    title = one("ProductIdentityTitle")["name"]
                    publisher = one("PublisherNameLink")["name"]
                    action = one("AcquireNewProduct")
                    if title != query or not re.search(r"\bFree\b", search_evidence):
                        raise ValueError("Exact title and explicitly free search-result evidence are required")
                    preview = ActionPreview.create(app.id, "software.install", {
                        "application": title, "publisher": publisher, "source": "Microsoft Store", "cost": "free",
                        "cost_evidence": search_evidence, "action": action["name"],
                        "notice": "Preview only. Recheck current price and request approval before acquisition."})
                    print(json.dumps({"result": "READY_FOR_CONFIRMED_MANUAL_ACTION", "preview": preview.details,
                                      "install_attempted": False, "purchase_attempted": False}), flush=True)
                    return
            print(json.dumps({"store_open": True, "controls": [
                {key: control.get(key) for key in ("name", "control_type", "automation_id", "actions")}
                for control in desktop.observation["controls"]]}), flush=True)
        finally:
            await services.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
