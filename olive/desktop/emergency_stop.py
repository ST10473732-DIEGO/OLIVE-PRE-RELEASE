"""Immediate stop state shared with Windows helper processes."""

import os
import threading
import uuid


class EmergencyStop:
    def __init__(self):
        self.event = threading.Event()
        self.name = "Local\\OLIVEStop-" + uuid.uuid4().hex if os.name == "nt" else ""
        self.handle = None
        if self.name:
            import win32event
            self.handle = win32event.CreateEvent(None, True, False, self.name)

    def set(self):
        self.event.set()
        if self.handle:
            import win32event
            win32event.SetEvent(self.handle)

    def clear(self):
        if self.handle:
            import win32event
            win32event.ResetEvent(self.handle)
        self.event.clear()

    def is_set(self):
        return self.event.is_set()


def check_worker_stop(name):
    if not name:
        raise PermissionError("Desktop helper requires a task stop channel")
    import win32event
    import win32con
    handle = win32event.OpenEvent(win32con.SYNCHRONIZE, False, name)
    try:
        if win32event.WaitForSingleObject(handle, 0) == win32event.WAIT_OBJECT_0:
            raise InterruptedError("Desktop control stopped")
    finally:
        handle.Close()
