import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from olive.desktop.models import DesktopControlSession
from olive.desktop.universal_workflow import UniversalWorkflow, validate_plan, exact_control


def step(operation, **arguments):
    return {"operation": operation, "arguments": arguments}


class UniversalWorkflowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.desktop = Mock()
        self.desktop.operation = None
        self.desktop.record = DesktopControlSession("Fixture")
        self.desktop.status.return_value = {"status": "fixture"}
        self.desktop.browser_launch = AsyncMock(return_value=[{"id": "tab"}])
        self.desktop.browser_navigate = AsyncMock(return_value={"url": "https://example.test"})
        self.desktop.browser_observe = AsyncMock(return_value={"controls": [
            {"id": "field", "name": "Search"}, {"id": "file", "name": "Attachment"},
            {"id": "recipient", "name": "Recipient"}, {"id": "subject", "name": "Subject"},
            {"id": "body", "name": "Message"}, {"id": "send", "name": "Send"},
        ]})
        for name in ("browser_action", "browser_upload", "browser_send", "media_action", "discover_applications"):
            setattr(self.desktop, name, AsyncMock(return_value={"verified": True}))
        self.desktop.browser_download = AsyncMock(return_value={"download": {"id": "quarantined"}})
        self.desktop.save_download = AsyncMock(return_value={"success": True})
        self.desktop.media_sessions = AsyncMock(return_value=[{"application_id": "SomeMusic!App"}])
        self.desktop.open_application = AsyncMock(return_value={"verified": True})
        self.desktop.discovery.resolve.side_effect = lambda name: SimpleNamespace(id=name)
        self.workflow = UniversalWorkflow(self.desktop)

    def test_unknown_operations_and_extra_arguments_rejected(self):
        for steps in ([step("browser.eval", script="run")], [step("application.open", name="Test", shell="yes")]):
            with self.assertRaises(ValueError):
                validate_plan({"steps": steps})

    def test_ambiguous_controls_and_secret_controls_fail_closed(self):
        for controls in ([{"id": "a", "name": "Save"}, {"id": "b", "name": "Save"}],
                         [{"id": "a", "name": "Save", "password": True}]):
            with self.assertRaises(ValueError):
                exact_control(controls, "Save")

    async def test_browser_upload_and_media_sequence_uses_authorized_controllers(self):
        steps = [step("browser.open", channel="chrome", url="https://example.test"),
                 step("browser.upload", target="Attachment", path="fixture.pdf"),
                 step("media.control", application="SomeMusic", action="pause")]
        await self.workflow.run("Fixture", steps)
        self.desktop.browser_upload.assert_awaited_once_with("file", "fixture.pdf")
        self.desktop.media_action.assert_awaited_once_with("SomeMusic!App", "pause")
        self.assertEqual(len(self.workflow.history), 3)
        self.assertEqual(self.desktop.record.status, "completed")

    async def test_communication_always_uses_dedicated_preview(self):
        await self.workflow.run("Fixture", [step("browser.open", channel="chrome", url="https://example.test"),
            step("browser.send", destination_field="Recipient", subject_field="Subject", body_field="Message",
                 send_control="Send", expected="Sent")])
        self.desktop.browser_send.assert_awaited_once_with(
            {"destination": "recipient", "subject": "subject", "body": "body", "send": "send"}, "Sent")
        self.desktop.browser_action.assert_not_awaited()

    async def test_download_transfer_uses_only_current_workflow_quarantine_id(self):
        await self.workflow.run("Fixture", [step("browser.open", channel="chrome", url="https://example.test"),
            step("browser.download", target="Attachment"), step("download.save", destination="fixture.txt")])
        self.desktop.save_download.assert_awaited_once_with("quarantined", "fixture.txt")
        with self.assertRaisesRegex(ValueError, "No quarantined"):
            await self.workflow.run("Other task", [step("download.save", destination="other.txt")])

    async def test_failed_phase_stops_later_apps_and_preserves_history(self):
        self.desktop.browser_upload.side_effect = PermissionError("Denied")
        with self.assertRaises(PermissionError):
            await self.workflow.run("Fixture", [step("browser.open", channel="chrome", url="https://example.test"),
                step("browser.upload", target="Attachment", path="fixture.pdf"),
                step("media.control", application="SomeMusic", action="play")])
        self.desktop.media_action.assert_not_awaited()
        self.assertEqual(self.desktop.record.status, "PAUSED_REVIEW_REQUIRED")
        self.assertEqual(len(self.workflow.history), 1)

    async def test_app_a_b_a_resolves_each_application_again(self):
        await self.workflow.run("Fixture", [step("application.open", name=name) for name in ("A", "B", "A")])
        self.assertEqual([call.args[0] for call in self.desktop.open_application.await_args_list], ["A", "B", "A"])
        self.assertEqual(self.desktop.discover_applications.await_count, 3)

    async def test_cancel_stops_future_actions(self):
        self.desktop.browser_navigate.side_effect = asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError):
            await self.workflow.run("Fixture", [step("browser.open", channel="chrome", url="https://example.test"),
                step("media.control", application="SomeMusic", action="play")])
        self.desktop.media_action.assert_not_awaited()
        self.assertIsNone(self.workflow.owner)
        self.assertEqual(self.desktop.record.status, "cancelled")

    async def test_missing_or_multiple_tabs_requires_review(self):
        self.desktop.browser_launch.return_value = [{"id": "one"}, {"id": "two"}]
        with self.assertRaisesRegex(ValueError, "intended browser tab"):
            await self.workflow.run("Fixture", [step("browser.open", channel="chrome", url="https://example.test")])
        self.desktop.browser_navigate.assert_not_awaited()

    async def test_planner_cannot_invent_file_paths(self):
        self.desktop.s.ollama.chat_once = AsyncMock(return_value=json.dumps({"steps": [
            step("folder.open", path="private-data")]}))
        with self.assertRaisesRegex(ValueError, "exact file or folder path"):
            await self.workflow.plan("Open my documents")

    async def test_markdown_wrapped_model_output_is_rejected(self):
        self.desktop.s.ollama.chat_once = AsyncMock(return_value='```json\n{"steps": []}\n```')
        with self.assertRaises(ValueError):
            await self.workflow.plan("Open an app")

    async def test_pause_does_not_start_another_operation(self):
        self.workflow.paused = True
        import time
        task = asyncio.create_task(self.workflow.checkpoint(time.monotonic() + 1))
        await asyncio.sleep(.01)
        self.assertFalse(task.done())
        self.workflow.paused = False
        await task
