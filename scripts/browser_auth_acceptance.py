"""Visible approved OLIVE browser: login readiness or Compose, never Send."""
import asyncio
import json
from pathlib import Path
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from olive.application.service_container import ServiceContainer
from olive.agent.confirmation_service import ConfirmationResponse
from olive.config import DATA_DIR


async def main():
    with tempfile.TemporaryDirectory(prefix="olive-browser-auth-") as directory:
        async def approve(request):
            return ConfirmationResponse(request.tool_name in {"desktop.control_application", "desktop.inspect_application", "network.read"})
        services = ServiceContainer(lambda *args: None, approve, data_dir=directory, migrate=False)
        try:
            desktop = services.desktop
            desktop.configure({"enabled": True})
            approved_profile = DATA_DIR / "interactive-browser"
            if approved_profile.exists():
                desktop.browser.provider.profile = approved_profile
            tabs = await desktop.browser_launch("chrome")
            tab_id = tabs[0]["id"]
            state = await desktop.browser_navigate(tab_id, "https://mail.google.com/")
            for _ in range(20):
                if state["authentication_state"] == "LOGIN_REQUIRED":
                    print(json.dumps({"result": "AUTHENTICATED_BROWSER_READY_BUT_LOGIN_REQUIRED",
                                      "credentials_read": False, "send_attempted": False}), flush=True)
                    return
                compose = [c for c in state["controls"] if c["name"].strip().casefold() == "compose"]
                if len(compose) == 1:
                    # Opening an empty compose panel is the entire authenticated test.
                    state = await desktop.browser_action(compose[0]["id"], "click", expected="Send")
                    print(json.dumps({"result": "AUTHENTICATED_COMPOSE_OPENED", "send_attempted": False,
                                      "subject_field": any(c["name"].casefold() == "subject" for c in state["controls"])}), flush=True)
                    return
                await asyncio.sleep(.3)
                state = await desktop.browser_observe(tab_id)
            raise RuntimeError("Browser reached a page, but login or authenticated Compose state was not verified")
        finally:
            await services.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
