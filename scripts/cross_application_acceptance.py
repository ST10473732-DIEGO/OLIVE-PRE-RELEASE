"""Owned adapter-free fixture used inside the live browser/context acceptance."""

import asyncio
from pathlib import Path
import subprocess
import sys
import time


async def return_to_browser(services, context):
    import psutil
    import win32gui
    import win32process
    from olive.desktop.windows_observation import enumerate_windows
    from olive.desktop.browser_focus import profile_windows
    desktop = services.desktop
    selected_file, tab = context.entities.get("path"), context.tab_id
    handle = win32gui.GetForegroundWindow()
    approved = {"hwnd": handle, "pid": win32process.GetWindowThreadProcessId(handle)[1]}
    process = subprocess.Popen([sys.executable, str(Path(__file__).with_name("desktop_test_app.py"))])
    owned = {process.pid}
    execute = services.interaction.router.execute
    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if process.poll() is None:
                owned.update(child.pid for child in psutil.Process(process.pid).children(recursive=True))
            await desktop.list_windows()
            found = next((key for key, window in desktop.windows.items() if window["pid"] in owned), None)
            if found:
                break
            await asyncio.sleep(.1)
        else:
            raise TimeoutError("Owned cross-application fixture did not appear")
        await desktop.inspect(found)
        session = desktop.sessions.sessions[desktop.sessions.current]
        assert not session.identity.adapter, "Fixture unexpectedly has an adapter"
        context.accept({"intent": "application.activate", "entities": {"application": session.identity.display_name}})
        async def handoff(step, state):
            await desktop.provider.call("activate", desktop.windows[found], expected_foreground=approved)
            return await execute(step, state)
        services.interaction.router.execute = handoff
        result = await services.interaction.submit("Put Browser return fixture in the Acceptance text field.")
        services.interaction.router.execute = execute
        observation = await desktop.gateway.observe(session)
        if not any(c.get("value") == "Browser return fixture" for c in observation["controls"]):
            raise AssertionError("Cross-application text entry failed: " + result["messages"][-1]["content"])
        if win32process.GetWindowThreadProcessId(win32gui.GetForegroundWindow())[1] not in owned:
            raise AssertionError("Fixture was not foreground before the natural browser return")
        result = await services.interaction.submit("Go back to Chrome.")
        windows = profile_windows(desktop.browser.provider.profile)
        if len(windows) != 1 or windows[0]["hwnd"] != win32gui.GetForegroundWindow():
            raise AssertionError("Natural browser return failed: " + result["messages"][-1]["content"]
                                 + "; interpretation=" + repr(context.last_interpretation))
        if context.tab_id != tab or context.entities.get("path") != selected_file:
            raise AssertionError("Browser return lost the tab or selected file identity")
    finally:
        services.interaction.router.execute = execute
        for window in enumerate_windows():
            if window["pid"] in owned:
                win32gui.PostMessage(window["hwnd"], 0x0010, 0, 0)
        try:
            await asyncio.to_thread(process.wait, timeout=5)
        except subprocess.TimeoutExpired:
            raise RuntimeError("Owned cross-application fixture did not close")
