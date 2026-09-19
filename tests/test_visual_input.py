import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from olive.desktop.visual_input import VisualInput, VisualClickTool, screen_point
from olive.agent.tool_schema import ToolContext


class VisualInputTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.old = Path(self.folder.name) / "old.png"
        self.old.write_bytes(b"original capture")
        self.new = Path(self.folder.name) / "new.png"
        self.new.write_bytes(b"changed capture")
        self.d = Mock()
        self.d.configuration.return_value = {"vision_fallback": True, "mouse_policy": "ask"}
        self.session = SimpleNamespace(task_id="task", window={"hwnd": 1}, identity=SimpleNamespace(display_name="Fixture"))
        self.d.sessions.current = "app"
        self.d.sessions.sessions = {"app": self.session}
        self.d.screenshots.records = {"capture": {"path": str(self.old), "task_id": "task", "window": {"hwnd": 1}, "client_bounds": {}}}
        self.d.screenshot = AsyncMock(return_value={"path": str(self.new), "client_bounds": {}})
        self.d.gateway.observe = AsyncMock(return_value={"controls": []})
        self.d.gateway.approval = AsyncMock()
        self.d.provider.call = AsyncMock()
        self.visual = VisualInput(self.d)
        self.visual.remember({"capture_id": "capture", "target_found": True, "confidence": .95,
                              "target_label": "Preview", "bounds": {"left": 0, "top": 0, "right": 10, "bottom": 10}})

    def test_mapping_uses_client_origin_across_negative_monitor_coordinates(self):
        capture = {"width": 100, "height": 50, "client_bounds": {"left": -1200, "top": 100, "right": -1000, "bottom": 200}}
        self.assertEqual(screen_point(capture, {"left": 40, "top": 20, "right": 60, "bottom": 30}), (-1100, 150))
        with self.assertRaises(ValueError):
            screen_point(capture, {"left": 90, "top": 0, "right": 110, "bottom": 10})

    async def test_changed_pixels_after_review_never_reach_input(self):
        with self.assertRaisesRegex(ValueError, "pixels changed"):
            await self.visual.click("capture", "Verified")
        self.d.provider.call.assert_not_awaited()

    async def test_model_cannot_enable_mouse_input(self):
        self.d.configuration.return_value["mouse_policy"] = "deny"
        with self.assertRaises(PermissionError):
            await self.visual.click("capture", "Verified")
        self.d.gateway.approval.assert_not_awaited()

    async def test_semantic_control_prevents_unnecessary_visual_click(self):
        self.d.gateway.observe.return_value = {"controls": [{"name": "Preview", "actions": ["invoke"]}]}
        with self.assertRaisesRegex(ValueError, "semantic invocation"):
            await self.visual.click("capture", "Verified")
        self.d.gateway.approval.assert_not_awaited()

    async def test_consequential_visual_target_requires_its_own_flow(self):
        self.visual.proposals["capture"]["target_label"] = "Send email"
        with self.assertRaisesRegex(PermissionError, "semantic preview"):
            await self.visual.click("capture", "Verified")

    async def test_wrong_task_capture_is_rejected(self):
        self.d.screenshots.records["capture"]["task_id"] = "another task"
        with self.assertRaisesRegex(PermissionError, "another task"):
            await self.visual.click("capture", "Verified")

    async def test_direct_tool_has_no_input_authority(self):
        with self.assertRaises(PermissionError):
            await VisualClickTool(self.d).execute({}, ToolContext("task"))
        self.d.provider.call.assert_not_awaited()

    async def test_emergency_stop_prevents_even_authorized_mouse_dispatch(self):
        import asyncio
        tool = VisualClickTool(self.d)
        self.d.gateway.check.side_effect = asyncio.CancelledError("Stopped")
        with self.assertRaises(asyncio.CancelledError):
            await tool.execute({}, ToolContext("task", progress_callback=tool))
        self.d.provider.call.assert_not_awaited()
