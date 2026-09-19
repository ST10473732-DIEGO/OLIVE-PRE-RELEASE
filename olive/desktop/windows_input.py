"""Internal Unicode fallback. No planner-callable global keyboard API."""

import ctypes
from ctypes import wintypes

from .emergency_stop import check_worker_stop
from .windows_observation import verify_identity


class KeyboardInput(ctypes.Structure):
    _fields_ = [("vk", wintypes.WORD), ("scan", wintypes.WORD), ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("extra", ctypes.c_size_t)]


class MouseInput(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("data", wintypes.DWORD),
                ("flags", wintypes.DWORD), ("time", wintypes.DWORD), ("extra", ctypes.c_size_t)]


class InputUnion(ctypes.Union):
    _fields_ = [("keyboard", KeyboardInput), ("mouse", MouseInput)]


class Input(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("value", InputUnion)]


def submit_search(window, control, stop_name):
    """Internal Return key for the gateway's verified semantic search operation."""
    _press_return(window, control, stop_name)


def submit_reviewed_message(window, control, stop_name):
    """Internal one-shot input reached only through the bound consequence transaction."""
    _press_return(window, control, stop_name)


def _press_return(window, control, stop_name):
    check_worker_stop(stop_name)
    verify_identity(window, foreground=True)
    if not control.has_keyboard_focus():
        raise PermissionError("FocusLost: reviewed editor lost focus")
    _require_no_modifiers()
    send = ctypes.WinDLL("user32", use_last_error=True).SendInput
    send.argtypes = [wintypes.UINT, ctypes.POINTER(Input), ctypes.c_int]
    send.restype = wintypes.UINT
    events = (Input * 2)(Input(1, InputUnion(keyboard=KeyboardInput(13, 0, 0, 0, 0))),
                         Input(1, InputUnion(keyboard=KeyboardInput(13, 0, 2, 0, 0))))
    if send(2, events, ctypes.sizeof(Input)) != 2:
        raise RuntimeError("Windows rejected the reviewed submission")
    verify_identity(window, foreground=True)


def _require_no_modifiers():
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    if any(user32.GetAsyncKeyState(key) & 0x8000 for key in (16, 17, 18, 91, 92)):
        raise PermissionError("A keyboard modifier is held; input stopped for user takeover")


def focus_editor_pointer(window, control, stop_name):
    """Place the caret inside a fresh accessible editor, with separately reviewed mouse input."""
    import win32gui
    from .windows_observation import physical_coordinates
    with physical_coordinates():
        verify_identity(window, foreground=True)
        _require_no_modifiers()
        rect = control.rectangle()
        client = win32gui.GetClientRect(window["hwnd"])
        origin = win32gui.ClientToScreen(window["hwnd"], (0, 0))
        end = win32gui.ClientToScreen(window["hwnd"], (client[2], client[3]))
        bounds = dict(zip(("left", "top", "right", "bottom"), (*origin, *end)))
        if (rect.width() <= 0 or rect.height() <= 0 or rect.left < origin[0] or rect.top < origin[1]
                or rect.right > end[0] or rect.bottom > end[1]):
            raise PermissionError("The editor is outside the verified client area")
        point = [int((rect.left + rect.right) / 2), int((rect.top + rect.bottom) / 2)]
        from pywinauto import Desktop
        hit = Desktop(backend="uia").from_point(*point)
        if hit.element_info.control_type not in {"Edit", "Text", "Document"}:
            raise PermissionError("Another control obscures the reviewed editor")
        wanted = tuple(control.element_info.runtime_id)
        for _ in range(8):
            if tuple(hit.element_info.runtime_id) == wanted:
                break
            hit = hit.parent()
            if hit is None:
                raise PermissionError("Another control obscures the reviewed editor")
        else:
            raise PermissionError("Another control obscures the reviewed editor")
        if control.rectangle() != rect:
            raise PermissionError("The reviewed editor moved before caret placement")
        click_window(window, point, bounds, stop_name)


def replace_empty_or_identical_editor(window, control, text, previous, stop_name, read_value, expected_previous=None):
    """Use real input events; a different value requires an explicit old-value binding."""
    if (not isinstance(text, str) or len(text) > 5000 or any(ord(ch) < 32 for ch in text)
            or (expected_previous is None and previous not in {"", text})
            or (expected_previous is not None and previous != expected_previous)):
        raise PermissionError("The editor does not match the reviewed previous text")
    check_worker_stop(stop_name)
    verify_identity(window, foreground=True)
    if not control.has_keyboard_focus():
        raise PermissionError("The reviewed editor lost focus")
    _require_no_modifiers()
    if previous:
        send = ctypes.WinDLL("user32", use_last_error=True).SendInput
        send.argtypes = [wintypes.UINT, ctypes.POINTER(Input), ctypes.c_int]
        send.restype = wintypes.UINT
        keys = [(17, 0), (65, 0), (65, 2), (17, 2), (8, 0), (8, 2)]
        events = (Input * len(keys))(*(Input(1, InputUnion(keyboard=KeyboardInput(key, 0, flags, 0, 0))) for key, flags in keys))
        if send(len(events), events, ctypes.sizeof(Input)) != len(events):
            raise RuntimeError("Windows rejected replacement in the reviewed editor")
        import time
        deadline = time.monotonic() + 2
        while read_value(control):
            check_worker_stop(stop_name)
            verify_identity(window, foreground=True)
            if not control.has_keyboard_focus():
                raise PermissionError("The reviewed editor did not clear; text entry stopped")
            if time.monotonic() >= deadline:
                raise PermissionError("The reviewed editor did not clear; text entry stopped")
            time.sleep(.05)
    type_unicode(window, control, text, stop_name)


def type_unicode(window, control, text, stop_name):
    if not isinstance(text, str) or len(text) > 5000 or any(ord(char) < 32 for char in text):
        raise ValueError("Fallback accepts bounded printable text only")
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    send = user32.SendInput
    send.argtypes = [wintypes.UINT, ctypes.POINTER(Input), ctypes.c_int]
    send.restype = wintypes.UINT
    key_for = user32.VkKeyScanW
    key_for.argtypes = [wintypes.WCHAR]
    key_for.restype = ctypes.c_short
    for character in text:
        check_worker_stop(stop_name)
        verify_identity(window, foreground=True)
        if not control.has_keyboard_focus():
            raise PermissionError("FocusLost: input stopped because the target control lost focus")
        _require_no_modifiers()
        key = key_for(character) if ord(character) < 128 else -1
        if key >= 0 and key >> 8 in {0, 1}:
            # Printable layout keys produce ordinary key/beforeinput events in
            # rich web editors; Unicode packet events remain the fallback.
            keys = ([(16, 0)] if key >> 8 else []) + [(key & 255, 0), (key & 255, 2)] + ([(16, 2)] if key >> 8 else [])
            events = (Input * len(keys))(*(Input(1, InputUnion(keyboard=KeyboardInput(vk, 0, flags, 0, 0))) for vk, flags in keys))
            if send(len(events), events, ctypes.sizeof(Input)) != len(events):
                raise RuntimeError("Windows rejected text input")
            continue
        encoded = character.encode("utf-16-le")
        units = [int.from_bytes(encoded[index:index + 2], "little") for index in range(0, len(encoded), 2)]
        events = (Input * (len(units) * 2))()
        for index, unit in enumerate(units):
            events[index * 2] = Input(1, InputUnion(keyboard=KeyboardInput(0, unit, 4, 0, 0)))
            events[index * 2 + 1] = Input(1, InputUnion(keyboard=KeyboardInput(0, unit, 6, 0, 0)))
        if send(len(events), events, ctypes.sizeof(Input)) != len(events):
            raise RuntimeError("Windows rejected text input")
    verify_identity(window, foreground=True)


def click_window(window, point, client_bounds, stop_name):
    """One internal click, restricted to the fresh foreground window's client area."""
    import win32gui
    import win32api
    from .windows_observation import physical_coordinates
    if not isinstance(point, list) or len(point) != 2 or any(type(value) is not int for value in point):
        raise ValueError("Invalid click point")
    with physical_coordinates():
        current = verify_identity(window, foreground=True)
        if current["bounds"] != window["bounds"] or current["dpi"] != window["dpi"]:
            raise PermissionError("Window geometry changed before input")
        rect = win32gui.GetClientRect(window["hwnd"])
        origin = win32gui.ClientToScreen(window["hwnd"], (0, 0))
        end = win32gui.ClientToScreen(window["hwnd"], (rect[2], rect[3]))
        actual = dict(zip(("left", "top", "right", "bottom"), (*origin, *end)))
        x, y = point
        if actual != client_bounds or not origin[0] <= x < end[0] or not origin[1] <= y < end[1]:
            raise PermissionError("Click is outside the reviewed client area")
        hit = win32gui.WindowFromPoint((x, y))
        if win32gui.GetAncestor(hit, 2) != window["hwnd"]:
            raise PermissionError("Another window obscures the visual target")
        check_worker_stop(stop_name)
        verify_identity(window, foreground=True)
        win32api.SetCursorPos((x, y))
        check_worker_stop(stop_name)
        verify_identity(window, foreground=True)
        if win32api.GetCursorPos() != (x, y):
            raise PermissionError("User takeover changed the pointer")
        send = ctypes.WinDLL("user32", use_last_error=True).SendInput
        send.argtypes = [wintypes.UINT, ctypes.POINTER(Input), ctypes.c_int]
        send.restype = wintypes.UINT
        events = (Input * 2)(Input(0, InputUnion(mouse=MouseInput(0, 0, 0, 2, 0, 0))),
                             Input(0, InputUnion(mouse=MouseInput(0, 0, 0, 4, 0, 0))))
        if send(2, events, ctypes.sizeof(Input)) != 2:
            raise RuntimeError("Windows rejected the reviewed click")
        verify_identity(window, foreground=True)
