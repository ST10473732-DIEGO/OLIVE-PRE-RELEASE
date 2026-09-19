"""Read-only Win32 window enumeration with explicit physical-screen geometry."""

import os
from contextlib import contextmanager
from pathlib import Path
from .models import timestamp


def require_windows():
    if os.name != "nt":
        raise RuntimeError("Windows desktop observation is unavailable on this platform")


@contextmanager
def physical_coordinates():
    """Set only the calling thread's DPI context, preserving Qt's process policy."""
    require_windows()
    import ctypes
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    switch = user32.SetThreadDpiAwarenessContext
    switch.argtypes = [ctypes.c_void_p]
    switch.restype = ctypes.c_void_p
    previous = switch(ctypes.c_void_p(-4))
    if not previous:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        yield
    finally:
        if not switch(previous):
            raise ctypes.WinError(ctypes.get_last_error())


def inspect_window(hwnd):
    with physical_coordinates():
        result = _inspect_window(hwnd)
        if result["window_class"] == "ApplicationFrameWindow" and Path(result["executable"]).name.casefold() == "applicationframehost.exe":
            import win32gui
            candidates = []
            def child(handle, unused):
                if len(candidates) < 8 and win32gui.GetClassName(handle) == "Windows.UI.Core.CoreWindow":
                    item = _inspect_window(handle)
                    if item["package_identity"]:
                        candidates.append(item)
                return True
            win32gui.EnumChildWindows(hwnd, child, None)
            if len(candidates) == 1:
                from .window_identity import merge_hosted_window
                result = merge_hosted_window(result, candidates[0])
        return result


def _inspect_window(hwnd):
    require_windows()
    import win32gui
    import win32process
    import win32con
    import ctypes
    import psutil
    if not win32gui.IsWindow(hwnd):
        raise ValueError("Target window no longer exists")
    _, pid = win32process.GetWindowThreadProcessId(hwnd)
    try:
        process = psutil.Process(pid)
        executable = process.exe()
        process_created = process.create_time()
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        executable = ""
        process_created = None
    bounds = win32gui.GetWindowRect(hwnd)
    placement = win32gui.GetWindowPlacement(hwnd)
    get_dpi = ctypes.windll.user32.GetDpiForWindow
    get_dpi.argtypes = [ctypes.c_void_p]
    get_dpi.restype = ctypes.c_uint
    from .windows_app_identity import process_application_id
    return {"hwnd": hwnd, "pid": pid, "process_created": process_created, "title": win32gui.GetWindowText(hwnd)[:1000],
            "owner_hwnd": win32gui.GetWindow(hwnd, win32con.GW_OWNER),
            "window_class": win32gui.GetClassName(hwnd),
            "package_identity": process_application_id(pid),
            "executable": executable, "application": Path(executable).stem.casefold(),
            "bounds": dict(zip(("left", "top", "right", "bottom"), bounds)),
            "coordinate_system": "physical_screen_pixels", "dpi": get_dpi(hwnd) or 96,
            "foreground": win32gui.GetForegroundWindow() == hwnd,
            "minimized": bool(win32gui.IsIconic(hwnd)),
            "maximized": placement[1] == win32con.SW_SHOWMAXIMIZED,
            "visible": bool(win32gui.IsWindowVisible(hwnd)), "timestamp": timestamp(), "untrusted_content": True}


def enumerate_windows():
    require_windows()
    import win32gui
    windows = []

    def visit(hwnd, extra):
        if len(windows) >= 200:
            return True
        if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd):
            try:
                windows.append(inspect_window(hwnd))
            except (ValueError, OSError):
                # A window may disappear during the enumeration snapshot.
                return True
        return True

    win32gui.EnumWindows(visit, None)
    hosted_content = {item["content_hwnd"] for item in windows if item.get("content_hwnd")}
    return [item for item in windows if item["hwnd"] not in hosted_content]


def windows_for_processes(processes, diagnostic=None):
    """Read PID first; never read unrelated window titles, metadata or UI trees."""
    require_windows()
    import win32gui
    import win32process
    windows = []
    counts = diagnostic if diagnostic is not None else {}
    counts.update(owned_handles=0, invisible=0, empty_title=0, returned=0)
    def visit(hwnd, unused):
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if pid not in processes:
            return True
        counts['owned_handles'] += 1
        if win32gui.IsWindowVisible(hwnd):
            value = inspect_window(hwnd)
            if value['process_created'] != processes[pid]:
                raise PermissionError('Target process lifetime changed')
            if value['title']:
                windows.append(value)
                counts['returned'] += 1
            else:
                counts['empty_title'] += 1
        else:
            counts['invisible'] += 1
        return True
    win32gui.EnumWindows(visit, None)
    return windows


def verify_identity(target, foreground=False):
    value = inspect_window(target["hwnd"])
    if target.get('process_created') is not None and value.get('process_created') != target['process_created']:
        raise PermissionError('Target process lifetime changed; input stopped')
    if value["pid"] != target["pid"] or (target.get("executable") and os.path.normcase(value["executable"]) != os.path.normcase(target["executable"])):
        raise PermissionError("Window identity changed; review the target again")
    if any(value.get(key) != target.get(key) for key in ("host_pid", "content_hwnd", "package_identity") if key in target):
        raise PermissionError("Window identity changed; review the target again")
    if foreground and not value["foreground"]:
        raise PermissionError("Target lost foreground focus; input stopped")
    return value


def monitors():
    require_windows()
    import win32api
    return [{"bounds": dict(zip(("left", "top", "right", "bottom"), rect)),
             "coordinate_system": "physical_screen_pixels", "name": win32api.GetMonitorInfo(handle)["Device"]}
            for handle, _, rect in win32api.EnumDisplayMonitors()]
