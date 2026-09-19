"""Optional Windows emergency hotkey; the Qt stop button is always available."""

import ctypes
from ctypes import wintypes
import os
from PySide6.QtCore import QAbstractNativeEventFilter
from PySide6.QtGui import QGuiApplication


class DesktopStopHotkey(QAbstractNativeEventFilter):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback
        self.registered = False
        self.identifier = 0xDD34

    def configure(self, enabled):
        if os.name != "nt" or QGuiApplication.platformName() in {"offscreen", "minimal"} or enabled == self.registered:
            return self.registered
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        if enabled:
            user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
            user32.RegisterHotKey.restype = wintypes.BOOL
            self.registered = bool(user32.RegisterHotKey(None, self.identifier, 0x4003, 0x1B))
        else:
            user32.UnregisterHotKey(None, self.identifier)
            self.registered = False
        return self.registered

    def nativeEventFilter(self, event_type, message):
        if os.name == "nt" and self.registered:
            value = wintypes.MSG.from_address(int(message))
            if value.message == 0x0312 and value.wParam == self.identifier:
                self.callback()
                return True, 0
        return False, 0
