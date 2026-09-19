"""Bind interactive DOM actions to the visible, OLIVE-owned browser window."""

import asyncio
import os
from pathlib import Path


def profile_windows(profile):
    import psutil
    from .windows_observation import enumerate_windows
    wanted = os.path.normcase(str(Path(profile).resolve()))
    owners = set()
    for process in psutil.process_iter(["pid", "name"]):
        if process.info["name"].casefold() not in {"chrome.exe", "msedge.exe"}:
            continue
        try:
            # Inspect only the profile argument; never return/log command lines.
            paths = [argument.partition("=")[2] for argument in process.cmdline()
                     if argument.startswith("--user-data-dir=")]
            if any(os.path.normcase(str(Path(path).resolve())) == wanted for path in paths):
                owners.add(process.pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    # Owned bubbles/tooltips are not independent browser workspaces. If one owns
    # focus, prepare still refuses input until the user dismisses it.
    return [window for window in enumerate_windows() if window["pid"] in owners and not window.get("owner_hwnd")]


class BrowserFocusGuard:
    def __init__(self, provider, stop):
        self.provider, self.stop = provider, stop
        self.ui_owner = lambda pid: pid == os.getpid()

    async def prepare(self, profile, approved_foreground=None):
        from .windows_observation import verify_identity
        import win32gui
        import win32process
        if self.stop.is_set():
            raise InterruptedError("Desktop control stopped")
        windows = await asyncio.to_thread(profile_windows, profile)
        if len(windows) != 1:
            raise PermissionError("Select one visible OLIVE browser window; its target is ambiguous or unavailable")
        target = windows[0]
        foreground = win32gui.GetForegroundWindow()
        owner = win32process.GetWindowThreadProcessId(foreground)[1] if foreground else 0
        if foreground != target["hwnd"]:
            approved_switch = approved_foreground == {"hwnd": foreground, "pid": owner}
            if not self.ui_owner(owner) and not approved_switch:
                raise PermissionError("Browser control paused because focus changed")
            await self.provider.call("activate", target,
                                     expected_foreground={"hwnd": foreground, "pid": owner})
        verify_identity(target, foreground=True)
        if self.stop.is_set():
            raise InterruptedError("Desktop control stopped")
        return target

    def verify(self, target):
        from .windows_observation import verify_identity
        if self.stop.is_set():
            raise InterruptedError("Desktop control stopped")
        verify_identity(target, foreground=True)
