"""Explicit live window capture -> installed vision -> reviewed click -> UIA check."""
import asyncio
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import psutil
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from olive.application.service_container import ServiceContainer
from olive.agent.confirmation_service import ConfirmationResponse


def fixture_target(capture):
    """Test-only expected geometry from the owned fixture's exact paint color."""
    with Image.open(capture["path"]) as source:
        image = source.convert("RGB")
        points = [(x, y) for y in range(image.height) for x in range(image.width)
                  if image.getpixel((x, y)) == (52, 103, 173)]
    if not points:
        raise AssertionError("Owned visual fixture did not finish painting")
    left, right = min(x for x, _ in points), max(x for x, _ in points) + 1
    top, bottom = min(y for _, y in points), max(y for _, y in points) + 1
    return {"left": left, "right": right, "top": top, "bottom": bottom}


async def main():
    process = subprocess.Popen([sys.executable, str(Path(__file__).with_name("visual_test_app.py"))])
    owned = {process.pid}
    services = None
    temporary = tempfile.TemporaryDirectory(prefix="olive-visual-acceptance-")
    try:
        if temporary:
            folder = temporary.name
            async def approve(request):
                return ConfirmationResponse(request.tool_name in {"desktop.inspect_application", "desktop.control_application",
                                                                  "desktop.view_screen", "desktop.mouse_input"})
            services = ServiceContainer(lambda *args: None, approve, data_dir=folder, migrate=False)
            desktop = services.desktop
            desktop.configure({"enabled": True, "mouse_policy": "ask", "screen_observation": True, "vision_fallback": True})
            policies = services.permissions.policies()
            policies["permissions"]["desktop.view_screen"] = "ask"
            services.permissions.save(policies["permissions"], policies["scopes"])
            deadline = time.monotonic() + 15
            found = None
            while time.monotonic() < deadline:
                if process.poll() is None:
                    owned.update(child.pid for child in psutil.Process(process.pid).children(recursive=True))
                await desktop.list_windows()
                found = next((key for key, value in desktop.windows.items() if value["pid"] in owned), None)
                if found:
                    break
                await asyncio.sleep(.1)
            if not found:
                raise TimeoutError("Visual fixture did not appear")
            await desktop.inspect(found)
            if "--verify-label" in sys.argv:
                await services.model_registry.refresh()
                result = await desktop.vision_verify_label("Preview")
                if not result["verified"]:
                    raise AssertionError("Installed vision model did not verify the fixture label")
                print(json.dumps(result), flush=True)
                return
            input_only = "--input-only" in sys.argv
            if input_only:
                capture = await desktop.screenshot()
                if "--capture-debug" in sys.argv:
                    artifact = Path(__file__).resolve().parents[1] / ".qt-smoke" / "visual-fixture.png"
                    artifact.parent.mkdir(exist_ok=True)
                    artifact.write_bytes(Path(capture["path"]).read_bytes())
                proposal = {"capture_id": capture["id"], "target_found": True, "confidence": 1,
                            "target_label": "Preview", "model": None,
                            "bounds": fixture_target(capture)}
                desktop.visual.remember(proposal)
            else:
                await services.model_registry.refresh()
                proposal = await desktop.vision_observe("Find the blue Preview button. Return its exact bounding rectangle.")
            if not proposal["target_found"]:
                raise AssertionError("Installed vision model did not find the target")
            result = await desktop.visual_click(proposal["capture_id"], "Visual interaction verified")
            if not result["verified"]:
                raise AssertionError("Visual click was not semantically verified")
            print(json.dumps({"model": proposal["model"], "vision_used": not input_only, "fixture_defined_target": input_only,
                              "capture_scoped": True, "reviewed_click_verified": True,
                              "dedicated_adapter": False}), flush=True)
            await services.shutdown()
            services = None
    finally:
        if services:
            await services.shutdown()
        import win32gui
        import win32con
        from olive.desktop.windows_observation import enumerate_windows
        for window in enumerate_windows():
            if window["pid"] in owned:
                win32gui.PostMessage(window["hwnd"], win32con.WM_CLOSE, 0, 0)
        process.wait(timeout=5)
        if any(window["pid"] in owned for window in enumerate_windows()):
            raise RuntimeError("Visual fixture cleanup did not complete")
        temporary.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
