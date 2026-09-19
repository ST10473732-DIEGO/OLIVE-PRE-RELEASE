"""Live focus-loss and stop checks against owned harmless fixture windows."""
import asyncio
from pathlib import Path
import subprocess
import sys
import time
import psutil
from olive.desktop.workflow import DesktopStep


async def check(desktop, target):
    session = desktop.sessions.sessions[desktop.sessions.current]
    app = session.key
    steps = [DesktopStep(app, "set_text", target, {"text": "Step " + str(index)},
                         {**target, "value": "Step " + str(index)}, "desktop.keyboard_input") for index in range(8)]
    async def stop_later():
        await asyncio.sleep(.8)
        desktop.stop()
    stopper = asyncio.create_task(stop_later())
    cancelled = False
    try:
        await desktop._run_steps(steps)
    except asyncio.CancelledError:
        cancelled = True
    await stopper
    if not cancelled or desktop.record.status != "cancelled":
        raise AssertionError("Emergency stop did not interrupt the sequence")
    desktop.reset()
    observation = await desktop.gateway.observe(session)
    value = next(item["value"] for item in observation["controls"] if item["runtime_id"] == target["runtime_id"])
    if value == "Step 7":
        raise AssertionError("The full sequence ran despite emergency stop")

    process = subprocess.Popen([sys.executable, str(Path(__file__).with_name("desktop_test_app.py"))])
    owned = {process.pid}
    try:
        deadline = time.monotonic() + 10
        other = None
        while time.monotonic() < deadline:
            owned.update(child.pid for child in psutil.Process(process.pid).children(recursive=True))
            await desktop.list_windows()
            other = next((window for window in desktop.windows.values() if window["pid"] in owned), None)
            if other:
                break
            await asyncio.sleep(.1)
        if not other:
            raise TimeoutError("Second fixture window was not discovered")
        await desktop.provider.call("activate", other)
        try:
            await desktop.perform("set_text", target, {"text": "Must not appear"}, {**target, "value": "Must not appear"})
        except PermissionError as error:
            if "focus changed" not in str(error):
                raise
        else:
            raise AssertionError("Unexpected app focus did not block input")
        observation = await desktop.gateway.observe(session)
        actual = next(item["value"] for item in observation["controls"] if item["runtime_id"] == target["runtime_id"])
        if actual != value:
            raise AssertionError("Focus-loss rejection changed the original editor")
        return {"emergency_stop_during_sequence": True, "focus_loss_blocks_input": True}
    finally:
        import win32gui
        import win32con
        from olive.desktop.windows_observation import enumerate_windows
        for window in enumerate_windows():
            if window["pid"] in owned:
                win32gui.PostMessage(window["hwnd"], win32con.WM_CLOSE, 0, 0)
        process.wait(timeout=5)
