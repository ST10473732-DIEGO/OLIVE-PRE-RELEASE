"""Installed adapter-free Calculator acceptance, excluding pre-existing windows."""

import asyncio
import json
from pathlib import Path
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from olive.application.service_container import ServiceContainer
from olive.agent.confirmation_service import ConfirmationResponse
from olive.desktop.windows_observation import enumerate_windows


async def main():
    before = enumerate_windows()
    if any("calculator" in window["application"].casefold() for window in before):
        raise RuntimeError("A Calculator window is already open; this test leaves it untouched")
    owned = None
    with tempfile.TemporaryDirectory(prefix="olive-calculator-acceptance-") as directory:
        async def approve(request):
            return ConfirmationResponse(request.tool_name in {"system.open_application", "desktop.inspect_application", "desktop.control_application"})
        services = ServiceContainer(lambda *args: None, approve, data_dir=directory, migrate=False)
        try:
            desktop = services.desktop
            desktop.configure({"enabled": True})
            await desktop.discover_applications()
            app = desktop.discovery.resolve("Calculator")
            try:
                result = await desktop.open_application(app.id)
            except PermissionError:
                import win32gui
                from olive.desktop.windows_observation import inspect_window
                foreground = inspect_window(win32gui.GetForegroundWindow())
                print(json.dumps({"focus_failure": {key: foreground[key] for key in ("application", "window_class", "hwnd", "pid")},
                                  "targets": [{key: window[key] for key in ("application", "window_class", "hwnd", "pid", "foreground", "owner_hwnd")}
                                              for window in desktop.windows.values() if "calculator" in window["application"].casefold()]}), flush=True)
                raise
            if not result["verified"]:
                raise AssertionError(result["message"])
            owned = desktop.observation["window"]
            controls = desktop.observation["controls"]
            if "--inspect" in sys.argv:
                print(json.dumps({"controls": [{"name": item["name"], "type": item["control_type"], "automation_id": item["automation_id"]} for item in controls]}))
                return
            value = await desktop.perform("invoke", {"name": "One", "control_type": "Button"}, {}, {"name": "Display is 1"})
            if value["session"]["status"] != "completed":
                raise AssertionError("Calculator result was not observed")
            print(json.dumps({"application": "Calculator", "adapter": None, "semantic_button_invoked": True, "result_verified": True}))
        finally:
            if owned is None:
                candidates = [window for window in services.desktop.windows.values()
                              if "calculator" in window["application"].casefold()
                              and window["hwnd"] not in {item["hwnd"] for item in before}]
                if len(candidates) == 1:
                    owned = candidates[0]
            if owned:
                import win32gui
                import win32con
                from olive.desktop.windows_observation import verify_identity
                verify_identity(owned)
                win32gui.PostMessage(owned["hwnd"], win32con.WM_CLOSE, 0, 0)
            await services.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
