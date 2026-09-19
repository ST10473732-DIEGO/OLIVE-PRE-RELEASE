"""Harmless Explorer/Settings checks, invoked by the live acceptance harness."""
import json
from pathlib import Path
import tempfile
import sys
from olive.application.service_container import ServiceContainer
from olive.agent.confirmation_service import ConfirmationResponse


async def main():
    with tempfile.TemporaryDirectory(prefix="olive-navigation-acceptance-") as folder:
        async def approve(request):
            return ConfirmationResponse(request.tool_name in {"filesystem.read", "app.file_explorer.navigate",
                "app.windows_settings.navigate", "desktop.inspect_application"})
        services = ServiceContainer(lambda *args: None, approve, data_dir=Path(folder) / "data", migrate=False)
        target = Path(folder) / "approved-test-directory"
        target.mkdir()
        try:
            services.desktop.configure({"enabled": True})
            result = await services.desktop.open_folder(str(target))
            print(json.dumps({"test": "explorer", "verified_actual_location": result["verified"]}), flush=True)
            # Close only Explorer windows whose current location still matches the test folder.
            current = await services.desktop.provider.call("verify_folder", {}, path=str(target))
            import win32gui
            import win32con
            for window in current["windows"]:
                win32gui.PostMessage(window["hwnd"], win32con.WM_CLOSE, 0, 0)
            if "--natural" in sys.argv:
                await services.model_registry.refresh()
                observed = []
                navigate = services.desktop.open_settings
                async def record(page):
                    result = await navigate(page)
                    observed.append(result)
                    return result
                services.desktop.open_settings = record
                reply = await services.interaction.submit("Take me to Bluetooth settings.")
                if len(observed) != 1 or not observed[0].get("verified"):
                    raise AssertionError("Natural Settings navigation failed: " + reply["messages"][-1]["content"])
                result = observed[0]
            else:
                result = await services.desktop.open_settings("bluetooth")
            print(json.dumps({"test": "settings", "verified_page": result["page"], "verified": result["verified"],
                              "configuration_changed": False}), flush=True)
        finally:
            await services.shutdown()
