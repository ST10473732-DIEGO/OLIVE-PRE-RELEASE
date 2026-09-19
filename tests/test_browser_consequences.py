import unittest
from unittest.mock import AsyncMock, Mock
from olive.desktop.browser_consequences import BrowserConsequences


class BrowserConsequenceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.fields = {key: key for key in ("destination", "subject", "body", "send")}
        self.values = {"destination": "alex@example.test", "subject": "Fixture", "body": "Reviewed text"}
        self.c = Mock()
        self.c.provider.targets = {key: ("tab", None, None, None) for key in self.fields}
        self.c.provider.pages = {"tab": Mock(url="https://example.test")}
        self.c.provider.target_signatures = {"send": {"label": "Send"}}
        self.c.provider.attachments = {}
        self.c.provider.attachment_names = AsyncMock(return_value=[])
        self.c.provider.target = AsyncMock()
        self.c.session.identity.id = "browser"
        self.c.desktop.gateway.approval = AsyncMock()
        self.c.focus.prepare = AsyncMock(return_value={})
        async def execute(operation, **arguments):
            if operation == "field_value":
                return self.values[arguments["target_id"]]
            return {"controls": [{"name": "Sent"}]}
        self.c.execute = AsyncMock(side_effect=execute)
        self.service = BrowserConsequences(self.c)

    async def test_send_requires_exact_preview_and_observed_postcondition(self):
        result = await self.service.send(self.fields, "Sent")
        self.assertTrue(result["verified"])
        approval = self.c.desktop.gateway.approval.await_args
        self.assertEqual(approval.args[1], "communication.send")
        self.assertEqual(approval.args[3]["destination"], self.values["destination"])
        self.assertEqual(approval.args[3]["body"], self.values["body"])
        self.assertTrue(approval.kwargs["always"])

    async def test_edited_draft_invalidates_approval(self):
        async def edit(*args, **kwargs):
            self.values["body"] = "Changed content"
        self.c.desktop.gateway.approval.side_effect = edit
        with self.assertRaisesRegex(PermissionError, "Draft changed"):
            await self.service.send(self.fields, "Sent")
        self.assertFalse(any(call.args[0] == "act" for call in self.c.execute.await_args_list))

    async def test_denied_send_never_clicks(self):
        self.c.desktop.gateway.approval.side_effect = PermissionError("Denied")
        with self.assertRaises(PermissionError):
            await self.service.send(self.fields, "Sent")
        self.assertFalse(any(call.args[0] == "act" for call in self.c.execute.await_args_list))

    async def test_ambiguous_recipient_never_reaches_confirmation(self):
        self.values["destination"] = "Alex"
        with self.assertRaisesRegex(ValueError, "recipient address"):
            await self.service.send(self.fields, "Sent")
        self.c.desktop.gateway.approval.assert_not_awaited()

    async def test_existing_success_label_is_not_proof_of_a_new_send(self):
        self.c.provider.target_signatures["old"] = {"label": "Sent"}
        with self.assertRaisesRegex(ValueError, "already present"):
            await self.service.send(self.fields, "Sent")
        self.c.desktop.gateway.approval.assert_not_awaited()

    async def test_revoked_application_permission_blocks_approved_send(self):
        self.c.desktop.gateway.require_not_denied.side_effect = PermissionError("revoked")
        with self.assertRaisesRegex(PermissionError, "revoked"):
            await self.service.send(self.fields, "Sent")
        self.assertFalse(any(call.args[0] == "act" for call in self.c.execute.await_args_list))

    async def test_changed_attachment_invalidates_send(self):
        self.c.provider.attachment_names.side_effect = [["reviewed.pdf"], ["different.pdf"]]
        with self.assertRaisesRegex(PermissionError, "Draft changed"):
            await self.service.send(self.fields, "Sent")
        self.assertFalse(any(call.args[0] == "act" for call in self.c.execute.await_args_list))
