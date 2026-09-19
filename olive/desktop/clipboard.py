"""Explicit clipboard operations; sensitive values never enter logs or persistence."""

import asyncio
import ctypes
import uuid
from .application_discovery import identity
from .application_sessions import ApplicationSession
from ..agent.tool_schema import ToolDefinition, ToolContext
from ..agent.tool_result import ToolResult


def clipboard_text(action, text="", stop=None):
    import win32clipboard
    import win32con
    win32clipboard.OpenClipboard()
    try:
        if stop and stop.is_set():
            raise InterruptedError("Desktop control stopped")
        if action == "read":
            if not win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
                raise ValueError("Clipboard does not contain plain text")
            size = ctypes.WinDLL("kernel32", use_last_error=True).GlobalSize
            size.argtypes, size.restype = [ctypes.c_void_p], ctypes.c_size_t
            handle = win32clipboard.GetClipboardDataHandle(win32con.CF_UNICODETEXT)
            if size(handle) > 32768:
                raise ValueError("Clipboard text exceeds the review limit")
            value = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
            if not isinstance(value, str) or len(value) > 8192:
                raise ValueError("Clipboard text exceeds the review limit")
            return {"text": value, "sensitive": True, "provenance": "explicit clipboard read"}
        if action != "write" or not isinstance(text, str) or len(text) > 8192 or "\x00" in text:
            raise ValueError("Invalid bounded clipboard text")
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardText(text, win32con.CF_UNICODETEXT)
        return {"verified": win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT) == text}
    finally:
        win32clipboard.CloseClipboard()


class ClipboardTool:
    def __init__(self, stop, action):
        self.stop, self.action = stop, action
        self.definition = ToolDefinition("desktop.clipboard_" + action, "Explicit clipboard operation", "desktop", {})

    async def execute(self, arguments, context):
        if context.progress_callback is not self or self.stop.is_set():
            raise PermissionError("Clipboard authorization required")
        return ToolResult(True, "Clipboard operation completed", await asyncio.to_thread(clipboard_text, self.action, arguments.get("text", ""), self.stop))


class ClipboardController:
    def __init__(self, desktop):
        self.desktop = desktop
        for action in ("read", "write"):
            desktop.s.tool_registry.register(ClipboardTool(desktop.stop_event, action))

    async def run(self, action, text=""):
        if action not in {"read", "write"}:
            raise ValueError("Unsupported clipboard operation")
        if not isinstance(text, str) or len(text) > 8192 or "\x00" in text:
            raise ValueError("Invalid bounded clipboard text")
        session = ApplicationSession(identity("Windows clipboard", "protocol", "clipboard"), str(uuid.uuid4()))
        await self.desktop.gateway.approval(session, "clipboard." + action, "Read clipboard text" if action == "read" else "Replace clipboard text",
            {"action": action, "characters": len(text) if action == "write" else "up to 8192"}, always=True)
        tool = self.desktop.s.tool_registry.require("desktop.clipboard_" + action)
        result = await tool.execute({"text": text}, ToolContext(session.task_id, progress_callback=tool))
        return result.data
