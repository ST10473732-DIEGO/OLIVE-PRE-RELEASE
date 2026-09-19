"""Real A → B → A UIA workflow, with two owned adapter-free fixture apps."""
import asyncio
from pathlib import Path
import subprocess
import sys
import time
import psutil
from olive.desktop.workflow import DesktopStep


async def check(desktop, first_target):
    first = desktop.sessions.sessions[desktop.sessions.current]
    process = subprocess.Popen([sys.executable, str(Path(__file__).with_name("desktop_test_app.py"))])
    owned = {process.pid}
    try:
        deadline = time.monotonic() + 10
        found = None
        while time.monotonic() < deadline:
            owned.update(child.pid for child in psutil.Process(process.pid).children(recursive=True))
            await desktop.list_windows()
            found = next((key for key, window in desktop.windows.items() if window["pid"] in owned), None)
            if found:
                break
            await asyncio.sleep(.1)
        if not found:
            raise TimeoutError("Second fixture was not discovered")
        await desktop.inspect(found)
        second = desktop.sessions.sessions[desktop.sessions.current]
        second_control = next(item for item in second.observations[-1]["controls"] if item["control_type"] == "Edit")
        second_target = {"runtime_id": second_control["runtime_id"]}
        await desktop.provider.call("activate", first.window)
        steps = [DesktopStep(session.key, "set_text", target, {"text": text}, {**target, "value": text},
                             "desktop.keyboard_input") for session, target, text in
                 ((first, first_target, "Alpha"), (second, second_target, "Beta"), (first, first_target, "Alpha again"))]
        result = await desktop._run_steps(steps)
        if result["session"]["status"] != "completed":
            raise AssertionError("Multi-application workflow did not complete")
        for session, target, expected in ((first, first_target, "Alpha again"), (second, second_target, "Beta")):
            observation = await desktop.gateway.observe(session)
            actual = next(item["value"] for item in observation["controls"] if item["runtime_id"] == target["runtime_id"])
            if actual != expected:
                raise AssertionError("An application did not retain its verified text")
        return {"multi_application_round_trip": True}
    finally:
        import win32gui
        import win32con
        from olive.desktop.windows_observation import enumerate_windows
        for window in enumerate_windows():
            if window["pid"] in owned:
                win32gui.PostMessage(window["hwnd"], win32con.WM_CLOSE, 0, 0)
        process.wait(timeout=5)
