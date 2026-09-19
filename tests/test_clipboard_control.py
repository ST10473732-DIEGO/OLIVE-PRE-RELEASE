import asyncio
import unittest
from unittest.mock import AsyncMock, Mock, patch
from olive.desktop.clipboard import ClipboardController, ClipboardTool
from olive.desktop.emergency_stop import EmergencyStop
from olive.agent.tool_schema import ToolContext
from olive.agent.tool_result import ToolResult


class ClipboardControlTests(unittest.IsolatedAsyncioTestCase):
    async def test_direct_tool_cannot_read_clipboard(self):
        tool = ClipboardTool(EmergencyStop(), "read")
        with patch("olive.desktop.clipboard.clipboard_text") as native:
            with self.assertRaises(PermissionError):
                await tool.execute({}, ToolContext("fixture"))
            native.assert_not_called()

    async def test_denied_read_does_not_touch_clipboard(self):
        desktop = Mock()
        desktop.gateway.approval = AsyncMock(side_effect=PermissionError("Denied"))
        controller = ClipboardController(desktop)
        with self.assertRaises(PermissionError):
            await controller.run("read")
        desktop.s.tool_registry.require.assert_not_called()

    async def test_sensitive_read_is_returned_without_persistence_or_audit_contents(self):
        desktop = Mock()
        desktop.gateway.approval = AsyncMock()
        tool = Mock(execute=AsyncMock(return_value=ToolResult(True, "Read", {"text": "private fixture", "sensitive": True})))
        desktop.s.tool_registry.require.return_value = tool
        value = await ClipboardController(desktop).run("read")
        self.assertTrue(value["sensitive"])
        self.assertNotIn("private fixture", str(desktop.gateway.approval.await_args))
        desktop.s.publish.assert_not_called()
        desktop.s.agent_audit.record.assert_not_called()

    async def test_invalid_text_never_reaches_confirmation(self):
        desktop = Mock()
        desktop.gateway.approval = AsyncMock()
        with self.assertRaises(ValueError):
            await ClipboardController(desktop).run("write", "invalid\x00value")
        desktop.gateway.approval.assert_not_awaited()
