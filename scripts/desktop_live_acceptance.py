"""Explicitly launched live UIA acceptance. Own test window and temporary data only."""

import asyncio
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import json
import psutil
import os
from contextlib import asynccontextmanager
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from olive.application.service_container import ServiceContainer
from olive.agent.confirmation_service import ConfirmationResponse


@asynccontextmanager
async def runtime_scope():
    with tempfile.TemporaryDirectory(prefix="olive-desktop-acceptance-") as folder:
        scope = SimpleNamespace(folder=folder, services=None)
        try:
            yield scope
        finally:
            if scope.services is not None:
                await scope.services.shutdown()


async def main():
    import win32gui
    import win32process
    foreground = win32gui.GetForegroundWindow()
    approved_foreground = {"hwnd": foreground, "pid": win32process.GetWindowThreadProcessId(foreground)[1]}
    notepad = "--notepad" in sys.argv
    before_pids = set(psutil.pids())
    command = [str(Path(os.environ.get("WINDIR", "C:/Windows")) / "System32/notepad.exe")] if notepad else [sys.executable, str(Path(__file__).with_name("desktop_test_app.py"))]
    if "--search" in sys.argv and not notepad:
        command.append("--search")
    if "--message" in sys.argv and not notepad:
        command.append("--message")
    process = subprocess.Popen(command)
    owned = {process.pid}
    try:
        async with runtime_scope() as scope:
            folder = scope.folder
            message_reviewed = False
            async def approve(request):
                nonlocal message_reviewed
                if request.tool_name == "communication.send" and "--message" in sys.argv and not notepad:
                    approved = (not message_reviewed and request.arguments.get("body") == "Hello from OLIVE"
                                and request.arguments.get("destination") == "OLIVE Generic Accessibility Acceptance")
                    message_reviewed = message_reviewed or approved
                    return ConfirmationResponse(approved)
                # Only this explicitly initiated harness uses fixed test approvals.
                if request.tool_name not in {"desktop.inspect_application", "desktop.keyboard_input", "desktop.control_application", "desktop.view_screen", "application.search"}:
                    return ConfirmationResponse(False)
                return ConfirmationResponse(True)
            services = ServiceContainer(lambda *args: None, approve, data_dir=folder, migrate=False)
            scope.services = services
            desktop = services.desktop
            desktop.configure({"enabled": True, "keyboard_policy": "ask"})
            services.permissions.save({"desktop.inspect_application": "allow", "desktop.keyboard_input": "ask",
                                       "desktop.control_application": "ask"})
            deadline = time.monotonic() + 15
            found = None
            while time.monotonic() < deadline:
                if process.poll() is None:
                    owned.update(child.pid for child in psutil.Process(process.pid).children(recursive=True))
                await desktop.list_windows()
                if notepad:
                    owned.update(item["pid"] for item in desktop.windows.values()
                                 if item["application"] == "notepad" and item["pid"] not in before_pids)
                found = next((key for key, item in desktop.windows.items() if item["pid"] in owned), None)
                if found:
                    break
                await asyncio.sleep(.1)
            if not found:
                raise TimeoutError("Fixture window did not appear")
            state = await desktop.inspect(found)
            # This explicitly initiated fixture test permits one initial handoff to its
            # own window. If the user changed focus since launch, activation fails closed.
            if "--natural" not in sys.argv:
                await desktop.provider.call("activate", desktop.windows[found], expected_foreground=approved_foreground)
            edits = [c for c in state["observation"]["controls"] if c["control_type"] in {"Edit", "Document"} and c.get("visible")]
            if len(edits) != 1:
                raise ValueError("Expected one real accessible edit control")
            target = {"runtime_id": edits[0]["runtime_id"]}
            if "--natural" in sys.argv:
                await services.model_registry.refresh()
                execute = services.interaction.router.execute
                first_action = True
                async def initial_handoff(step, context):
                    nonlocal first_action
                    print(json.dumps({"fixture_interpretation": step}), flush=True)
                    if first_action:
                        first_action = False
                        # Delay the single approved fixture handoff until interpretation
                        # completes, as the real Home window does before an action.
                        await desktop.provider.call("activate", desktop.windows[found], expected_foreground=approved_foreground)
                    return await execute(step, context)
                services.interaction.router.execute = initial_handoff
                reply = await services.interaction.submit("Please put Hello from OLIVE into the Acceptance text field.")
                current = desktop.sessions.sessions[desktop.sessions.current]
                observed = await desktop.gateway.observe(current)
                if not any(c.get("value") == "Hello from OLIVE" for c in observed["controls"]):
                    handle = win32gui.GetForegroundWindow()
                    owner = win32process.GetWindowThreadProcessId(handle)[1]
                    print(json.dumps({"failure_foreground_process": psutil.Process(owner).name(),
                                      "provider_error": getattr(desktop.provider, "last_error", None),
                                      "foreground_is_owned_fixture": owner in owned}), flush=True)
                    raise AssertionError("Natural request did not produce verified text: " + reply["messages"][-1]["content"])
                result = desktop.status()
            else:
                result = await desktop.perform("set_text", target, {"text": "Hello from OLIVE"},
                                               {**target, "value": "Hello from OLIVE"})
            if result["session"]["status"] != "completed":
                raise AssertionError("Text was not verified")
            result_record = {"test": "notepad" if notepad else "unknown_adapter_free_qt_app", "typed_text_verified": True,
                             "provider": desktop.provider.name}
            if "--natural" in sys.argv:
                result_record["natural_language_live_model_verified"] = True
            if "--search" in sys.argv and not notepad:
                searched = await desktop.perform("search", target, {"text": "Fixture query"}, {"name": "Search result: Fixture query"})
                result_record["generic_search_verified"] = searched["session"]["status"] == "completed"
            if "--message" in sys.argv and not notepad:
                current = desktop.sessions.sessions[desktop.sessions.current]
                observation = await desktop.gateway.observe(current)
                window = next(c for c in observation["controls"] if c["control_type"] == "Window")
                sent = await desktop.consequence("communication.send", target, {
                    "destination": [{"runtime_id": window["runtime_id"]}], "body": target},
                    {**target, "value": ""}, method="editor_enter")
                result_record["local_message_submission_verified"] = sent["verified"]
                result_record["semantic_send_reviewed"] = message_reviewed
            if "--safety" in sys.argv and not notepad:
                from desktop_safety_acceptance import check
                result_record.update(await check(desktop, target))
            if "--multi" in sys.argv and not notepad:
                from desktop_multi_acceptance import check
                result_record.update(await check(desktop, target))
            if "--capture" in sys.argv:
                desktop.configure({"enabled": True, "keyboard_policy": "ask", "screen_observation": True})
                policies = services.permissions.policies()
                policies["permissions"]["desktop.view_screen"] = "allow"
                services.permissions.save(policies["permissions"], policies["scopes"])
                capture = await desktop.screenshot()
                result_record["capture"] = {"width": capture["width"], "height": capture["height"]}
                if "--vision" in sys.argv:
                    from olive.desktop.vision import DesktopVision
                    await services.model_registry.refresh()
                    vision = await DesktopVision(services.ollama, services.model_router).observe(capture, "Find the Apply test text button.")
                    result_record["vision"] = {"model": vision["model"], "target_found": vision["target_found"],
                                                "target_label": vision["target_label"]}
                    await services.ollama.unload_model(vision["model"])
    finally:
        # Send a normal close only to the fixture PID created above.
        import win32gui
        import win32con
        from olive.desktop.windows_observation import enumerate_windows
        for window in enumerate_windows():
            if window["pid"] in owned:
                win32gui.PostMessage(window["hwnd"], win32con.WM_CLOSE, 0, 0)
        if notepad:
            from olive.desktop.uia_provider import WindowsUIAutomationProvider
            cleanup = WindowsUIAutomationProvider()
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if not any(window["pid"] in owned for window in enumerate_windows()):
                    break
                for window in enumerate_windows():
                    if window["pid"] not in owned:
                        continue
                    try:
                        observation = await cleanup.observe(window)
                    except ValueError:
                        # WM_CLOSE can complete while the observation helper starts.
                        # Only a vanished owned window is successful cleanup.
                        if not win32gui.IsWindow(window["hwnd"]):
                            continue
                        raise
                    buttons = [control for control in observation["controls"] if control["control_type"] == "Button"
                               and control["name"].replace("&", "").casefold() in {"don't save", "don’t save"}]
                    if len(buttons) == 1:
                        await cleanup.call("invoke", window, target={"runtime_id": buttons[0]["runtime_id"]})
                await asyncio.sleep(.1)
            await cleanup.close()
            if any(window["pid"] in owned for window in enumerate_windows()):
                raise RuntimeError("Notepad test window remains open; cleanup is not verified")
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            raise RuntimeError("Acceptance fixture did not close; review it manually")
    print(json.dumps({**result_record, "closed": True}), flush=True)


if __name__ == "__main__":
    if "--navigation" in sys.argv:
        from navigation_acceptance import main as navigation_main
        asyncio.run(navigation_main())
    else:
        asyncio.run(main())
