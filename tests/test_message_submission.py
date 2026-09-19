"""The editor fallback retains the same authoritative communication boundary."""

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from olive.desktop.message_submission import submit_editor_message
from olive.desktop.workflow import DesktopStep


class MessageSubmissionTests(unittest.IsolatedAsyncioTestCase):
    def fixture(self):
        title = {"runtime_id": "window", "name": "Example / room", "control_type": "Window", "visible": True, "enabled": True}
        editor = {"runtime_id": "body", "name": "Message room", "value": "hello", "control_type": "Edit", "visible": True, "enabled": True}
        before = {"controls": [title, editor]}
        after = {"controls": [title, {**editor, "value": ""}, {
            "runtime_id": "new-message", "name": "hello", "control_type": "Text", "visible": True}]}
        gateway = SimpleNamespace(require_uia=Mock(), check=Mock(), settings=lambda: {"keyboard_policy": "ask"},
            observe=AsyncMock(side_effect=[before, before, after]), approval=AsyncMock(), execute=AsyncMock(),
            fingerprint=Mock(return_value="bound-step"), permits={})
        session = SimpleNamespace(key="app", identity=SimpleNamespace(id="app", display_name="Example"), observe=Mock())
        desktop = SimpleNamespace(gateway=gateway, sessions=SimpleNamespace(current="app", sessions={"app": session}),
            stop_event=None, record=SimpleNamespace(), publish=Mock())
        target = {"runtime_id": "body"}
        return desktop, target, {"destination": [{"runtime_id": "window"}], "body": target}, before, after

    async def test_single_submission_requires_exact_preview_and_new_message_evidence(self):
        desktop, target, bindings, _, _ = self.fixture()
        result = await submit_editor_message(desktop, target, bindings)
        self.assertTrue(result["verified"])
        review = desktop.gateway.approval.await_args
        self.assertEqual(review.args[1], "communication.send")
        self.assertEqual(review.args[3]["body"], "hello")
        self.assertEqual(review.args[3]["destination"], "Example / room")
        self.assertTrue(review.kwargs["always"])
        desktop.gateway.execute.assert_awaited_once()
        self.assertEqual(desktop.gateway.execute.await_args.args[1].action, "submit_message")

    async def test_denied_communication_never_submits(self):
        desktop, target, bindings, _, _ = self.fixture()
        async def deny(session, permission, *args, **kwargs):
            if permission == "communication.send":
                raise PermissionError("Denied")
        desktop.gateway.approval.side_effect = deny
        with self.assertRaises(PermissionError):
            await submit_editor_message(desktop, target, bindings)
        desktop.gateway.execute.assert_not_awaited()

    async def test_execution_or_observation_failure_after_dispatch_is_uncertain(self):
        for failure in ("execution", "observation"):
            desktop, target, bindings, before, _ = self.fixture()
            if failure == "execution":
                desktop.gateway.execute.side_effect = PermissionError("Focus changed after input")
            else:
                desktop.gateway.observe.side_effect = [before, before, RuntimeError("Application closed")]
            with self.assertRaisesRegex(TimeoutError, "may have occurred"):
                await submit_editor_message(desktop, target, bindings)
            desktop.gateway.execute.assert_awaited_once()

    async def test_changed_destination_or_body_invalidates_approval(self):
        for field in ("destination", "body"):
            desktop, target, bindings, before, _ = self.fixture()
            changed = {"controls": [dict(c) for c in before["controls"]]}
            changed["controls"][0 if field == "destination" else 1]["name" if field == "destination" else "value"] = "Different"
            desktop.gateway.observe.side_effect = [before, changed]
            with self.assertRaisesRegex(PermissionError, "changed"):
                await submit_editor_message(desktop, target, bindings)
            desktop.gateway.execute.assert_not_awaited()

    async def test_empty_composer_alone_does_not_verify_or_retry(self):
        desktop, target, bindings, before, after = self.fixture()
        after["controls"].pop()
        desktop.gateway.observe.side_effect = [before, before, after]
        with patch("olive.desktop.message_submission.time", SimpleNamespace(monotonic=Mock(side_effect=[0, 0, 11]))):
            with self.assertRaises(TimeoutError):
                await submit_editor_message(desktop, target, bindings)
        desktop.gateway.execute.assert_awaited_once()

    async def test_existing_message_does_not_verify_new_submission(self):
        desktop, target, bindings, before, after = self.fixture()
        before["controls"].append(dict(after["controls"][-1]))
        with patch("olive.desktop.message_submission.time", SimpleNamespace(monotonic=Mock(side_effect=[0, 0, 11]))):
            with self.assertRaises(TimeoutError):
                await submit_editor_message(desktop, target, bindings)
        desktop.gateway.execute.assert_awaited_once()
        for call in desktop.gateway.observe.await_args_list:
            self.assertEqual(call.kwargs, {"control_limit": 1200, "depth_limit": 24})

    async def test_incomplete_snapshot_blocks_send_before_confirmation(self):
        desktop, target, bindings, before, _ = self.fixture()
        before["truncated"] = True
        with self.assertRaisesRegex(ValueError, "incomplete"):
            await submit_editor_message(desktop, target, bindings)
        desktop.gateway.execute.assert_not_awaited()
        desktop.gateway.approval.assert_not_awaited()

    async def test_keyboard_denial_stops_before_review_or_submission(self):
        desktop, target, bindings, _, _ = self.fixture()
        desktop.gateway.settings = lambda: {"keyboard_policy": "deny"}
        with self.assertRaises(PermissionError):
            await submit_editor_message(desktop, target, bindings)
        desktop.gateway.approval.assert_not_awaited()
        desktop.gateway.execute.assert_not_awaited()

    async def test_composer_child_is_not_delivery_evidence(self):
        desktop, target, bindings, before, after = self.fixture()
        after["controls"][-1]["parent_id"] = "body"
        desktop.gateway.observe.side_effect = [before, before, after]
        with patch("olive.desktop.message_submission.time", SimpleNamespace(monotonic=Mock(side_effect=[0, 0, 11]))):
            with self.assertRaises(TimeoutError):
                await submit_editor_message(desktop, target, bindings)
        desktop.gateway.execute.assert_awaited_once()

    async def test_generic_gateway_cannot_authorize_message_submission(self):
        from olive.desktop.gateway import DesktopGateway
        gateway = DesktopGateway.__new__(DesktopGateway)
        gateway.require_uia = Mock()
        step = DesktopStep("app", "submit_message", {"runtime_id": "body"}, {"text": "hello",
            "destination": [{"runtime_id": "window"}], "destination_text": "Example / room"}, {"value": ""}, "communication.send")
        with self.assertRaisesRegex(PermissionError, "dedicated consequence"):
            await gateway.authorize(SimpleNamespace(), step)

    def test_submission_cannot_use_an_ordinary_control_permission(self):
        with self.assertRaises(ValueError):
            DesktopStep("app", "submit_message", {}, {"text": "hello"}, {"value": ""}, "desktop.control_application")

    async def test_caret_placement_requires_mouse_review_and_obeys_denial(self):
        from olive.desktop.gateway import DesktopGateway
        desktop, target, _, before, _ = self.fixture()
        session = desktop.sessions.sessions["app"]
        session.observations = [before]
        gateway = DesktopGateway.__new__(DesktopGateway)
        gateway.require_uia = Mock()
        gateway.approval = AsyncMock()
        gateway.permits = {}
        gateway.fingerprint = Mock(return_value="bound-step")
        step = DesktopStep("app", "set_text", target, {"text": "hello", "pointer_focus": True},
                           {"value": "hello"}, "desktop.control_application")
        gateway.settings = lambda: {"mouse_policy": "deny", "keyboard_policy": "ask"}
        with self.assertRaises(PermissionError):
            await gateway.authorize(session, step)
        gateway.approval.assert_not_awaited()
        gateway.settings = lambda: {"mouse_policy": "ask", "keyboard_policy": "ask"}
        await gateway.authorize(session, step)
        mouse = [call for call in gateway.approval.await_args_list if call.args[1] == "desktop.mouse_input"]
        self.assertEqual(len(mouse), 1)
        self.assertTrue(mouse[0].kwargs["always"])

    async def test_uncertain_submission_cannot_be_replayed_or_replaced(self):
        from olive.interaction.router import CapabilityRouter
        router = CapabilityRouter(SimpleNamespace(desktop=SimpleNamespace()))
        router.communication.send = AsyncMock()
        pending = {"id": "same-action", "submission_uncertain": True, "entities": {"message": "hello"}}
        context = SimpleNamespace(pending=pending)
        for intent in ("communication.send", "communication.compose"):
            with self.assertRaisesRegex(ValueError, "unverified"):
                await router.execute({"intent": intent, "entities": {"message": "hello"}}, context)
        self.assertIs(context.pending, pending)
        router.communication.send.assert_not_awaited()

    async def test_native_timeout_marks_pending_delivery_uncertain(self):
        from olive.interaction.native_editor import send_from_editor
        desktop, _, _, before, _ = self.fixture()
        before["controls"][1]["actions"] = ["set_text"]
        desktop.consequence = AsyncMock(side_effect=TimeoutError("Unverified"))
        services = SimpleNamespace(desktop=desktop,
            model_router=SimpleNamespace(route=lambda request: SimpleNamespace(name="qwen3:8b", role="fast")),
            ollama=SimpleNamespace(chat_measured=AsyncMock(return_value={"content": '{"id":"body"}'})))
        pending = {"id": "same-action", "entities": {"channel": "room", "message": "hello"}}
        with self.assertRaises(TimeoutError):
            await send_from_editor(services, pending, desktop.sessions.sessions["app"], before)
        self.assertTrue(pending["submission_uncertain"])
        self.assertEqual(pending["state"], "verification_pending")
        self.assertEqual(pending["id"], "same-action")


class EditorInputTests(unittest.TestCase):
    def test_destination_evidence_rejects_channel_and_address_prefixes(self):
        from olive.desktop.verification import contains_destination
        self.assertFalse(contains_destination("#general-news | Example", "general"))
        self.assertFalse(contains_destination("john@example.test.evil", "john@example.test"))
        self.assertFalse(contains_destination("other+john@example.test", "john@example.test"))
        self.assertTrue(contains_destination("#general | Example", "general"))
        self.assertTrue(contains_destination("To: <john@example.test>", "john@example.test"))

    def test_caret_click_cannot_hit_an_overlaid_send_button(self):
        from contextlib import nullcontext
        from olive.desktop.windows_input import focus_editor_pointer
        rect = SimpleNamespace(left=0, top=0, right=100, bottom=20, width=lambda: 100, height=lambda: 20)
        editor = SimpleNamespace(rectangle=lambda: rect, element_info=SimpleNamespace(runtime_id=(1,)))
        overlay = SimpleNamespace(element_info=SimpleNamespace(control_type="Button", runtime_id=(2,)))
        win32 = SimpleNamespace(GetClientRect=lambda hwnd: (0, 0, 200, 200), ClientToScreen=lambda hwnd, point: point)
        uia = SimpleNamespace(Desktop=lambda **kwargs: SimpleNamespace(from_point=lambda *point: overlay))
        with patch.dict("sys.modules", {"win32gui": win32, "pywinauto": uia}), \
                patch("olive.desktop.windows_observation.physical_coordinates", return_value=nullcontext()), \
                patch("olive.desktop.windows_input.verify_identity"), \
                patch("olive.desktop.windows_input._require_no_modifiers"), \
                patch("olive.desktop.windows_input.click_window") as click:
            with self.assertRaisesRegex(PermissionError, "obscures"):
                focus_editor_pointer({"hwnd": 1}, editor, None)
        click.assert_not_called()

    def test_different_draft_is_never_erased(self):
        from olive.desktop.windows_input import replace_empty_or_identical_editor
        control = Mock()
        with self.assertRaises(PermissionError):
            replace_empty_or_identical_editor({}, control, "hello", "user draft", None, Mock())
        control.iface_value.SetValue.assert_not_called()

    def test_reviewed_replacement_rejects_intervening_user_edit(self):
        from olive.desktop.windows_input import replace_empty_or_identical_editor
        with self.assertRaises(PermissionError):
            replace_empty_or_identical_editor({}, Mock(), "hello", "user changed it", None,
                                             Mock(), expected_previous="earlier draft")

    def test_reviewed_replacement_types_only_after_old_text_clears(self):
        from olive.desktop.windows_input import replace_empty_or_identical_editor
        control = Mock()
        control.has_keyboard_focus.return_value = True
        user32 = Mock()
        user32.SendInput.return_value = 6
        with patch("olive.desktop.windows_input.ctypes.WinDLL", return_value=user32, create=True), \
                patch("olive.desktop.windows_input.verify_identity"), \
                patch("olive.desktop.windows_input.check_worker_stop"), \
                patch("olive.desktop.windows_input._require_no_modifiers"), \
                patch("olive.desktop.windows_input.type_unicode") as typing:
            replace_empty_or_identical_editor({}, control, "hello", "earlier draft", None,
                                             Mock(return_value=""), expected_previous="earlier draft")
        typing.assert_called_once_with({}, control, "hello", None)
        control.iface_value.SetValue.assert_not_called()

    def test_stale_accessibility_value_stops_without_overwriting_web_editor_state(self):
        from olive.desktop.windows_input import replace_empty_or_identical_editor
        control = Mock()
        control.has_keyboard_focus.return_value = True
        user32 = Mock()
        user32.SendInput.return_value = 6
        read = Mock(return_value="hello")
        with patch("olive.desktop.windows_input.ctypes.WinDLL", return_value=user32, create=True), \
                patch("olive.desktop.windows_input.verify_identity"), \
                patch("olive.desktop.windows_input.check_worker_stop"), \
                patch("olive.desktop.windows_input._require_no_modifiers"), \
                patch("olive.desktop.windows_input.type_unicode") as typing, \
                patch("time.monotonic", side_effect=[0, 3]):
            with self.assertRaises(PermissionError):
                replace_empty_or_identical_editor({}, control, "hello", "hello", None, read)
        control.iface_value.SetValue.assert_not_called()
        typing.assert_not_called()
