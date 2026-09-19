"""M1 request lifecycle and persistence boundaries without desktop automation."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication
from olive.ui_qt.feature_registry import default_registry
from olive.ui_qt.window_manager import WindowManager
from olive.models import Chat
from olive.application.chat_controller import ChatController

APP = QApplication.instance() or QApplication([])


class Bridge(QObject):
    event = Signal(str, object)
    confirmation = Signal(object)
    ready = Signal()
    stopped = Signal()
    is_ready = False

    def __init__(self):
        super().__init__(); self.calls = []

    def call(self, operation, callback=None, **arguments):
        self.calls.append((operation, callback, arguments))

    def stop_control(self): self.call("desktop.stop")


class ExperienceCoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.bridge = Bridge()
        self.manager = WindowManager(self.bridge, default_registry(), Path(self.temp.name)/"ui.json", presentation="midnight")
        self.c = self.manager.experience
        self.addCleanup(self.c.clock.stop)

    def test_duplicate_request_is_blocked_until_stream_finishes(self):
        self.c.submit("Explain this idea")
        self.c.submit("Explain this idea")
        self.assertEqual(len(self.bridge.calls), 1)
        self.bridge.calls[0][1]({"id":"chat-a"}, "")
        operation, callback, args = self.bridge.calls[-1]
        self.assertEqual(operation, "interaction.submit")
        callback({"generating":True,"messages":[{"role":"user","content":"Explain this idea"}]}, "")
        self.assertTrue(self.c.busy)
        self.assertEqual(self.c.result, "")
        self.c.submit("another request")
        self.assertEqual(len(self.bridge.calls), 2)
        self.bridge.event.emit("chat_stream", {"chat_id":"chat-a", "text":"An idea"})
        self.assertEqual(self.c.result, "An idea")
        self.bridge.event.emit("chat", {"id":"chat-b", "generating":False})
        self.assertTrue(self.c.busy)
        self.bridge.event.emit("chat", {"id":"chat-a", "generating":False,
            "messages":[{"role":"assistant","content":"An idea explained."}]})
        self.assertFalse(self.c.busy)
        self.assertEqual(self.c.result, "An idea explained.")

    def test_stale_callback_does_not_finish_new_request(self):
        self.c.submit("First")
        self.bridge.calls[0][1]({"id":"a"}, "")
        callback = self.bridge.calls[-1][1]
        callback(None, "Unavailable")
        self.c.submit("Second")
        callback(None, "old result")
        self.assertTrue(self.c.busy)
        self.assertNotEqual(self.c.result, "old result")

    def test_cancel_before_context_arrives_never_submits(self):
        self.c.submit("Open a workspace")
        callback = self.bridge.calls[0][1]
        self.c.cancel()
        callback({"id":"a"}, "")
        self.assertFalse(self.c.busy)
        self.assertFalse(any(call[0]=="interaction.submit" for call in self.bridge.calls))

    def test_late_confirmation_after_loop_teardown_is_inert(self):
        import asyncio
        from olive.ui_qt.runtime import RuntimeThread
        from olive.agent.confirmation_service import ConfirmationResponse
        worker = RuntimeThread()
        worker.loop = asyncio.new_event_loop(); worker.loop.close()
        worker.answer("expired", ConfirmationResponse(True))
        self.assertEqual(worker.pending_confirmations, {})

    def test_real_approval_precedes_activity_and_cannot_authorize(self):
        from olive.research.models import ResearchSession
        session = ResearchSession("Fixture question", id="r", status="searching")
        self.bridge.event.emit("research", session.to_dict())
        self.assertEqual(self.c.coreState, "RESEARCHING")
        self.c.on_confirmation(SimpleNamespace(id="approval"))
        self.assertEqual(self.c.coreState, "WAITING_FOR_APPROVAL")
        self.assertEqual(self.bridge.calls, [])
        self.c.confirmation_finished("approval")
        self.assertEqual(self.c.coreState, "RESEARCHING")
        self.bridge.event.emit("research", {"id":"r", "status":"completed"})
        self.assertEqual(self.c.coreState, "READY")

    def test_local_entry_does_not_require_model_and_preferences_persist(self):
        self.bridge.event.emit("status", {"ollama":"Unavailable", "chat_models":0})
        self.assertTrue(self.c.entryAllowed)
        self.c.enter(); self.assertFalse(self.c.welcome)
        self.c.setReducedMotion(True); self.c.togglePin("studio")
        self.assertTrue(self.manager.state.get("experience")["reduced_motion"])
        self.assertIn("studio", self.manager.state.get("experience")["favourites"])
        self.assertEqual(self.bridge.calls, [])

    def test_late_home_context_does_not_replace_newer_selection(self):
        self.c.refresh(); old = self.bridge.calls[-1][1]
        self.c.refresh(); new = self.bridge.calls[-1][1]
        new({"recent":[],"chat_id":"new","status":{},"context":{"file":"new.pdf"}}, "")
        old({"recent":[],"chat_id":"old","status":{},"context":{"file":"old.pdf"}}, "")
        self.assertEqual(self.c.contextLabel, "new.pdf")
        self.assertEqual(self.c._chat, "new")

    def test_draft_additive_round_trip_does_not_become_a_message(self):
        old = Chat.from_dict({"id":"legacy","messages":[{"role":"user","content":"existing"}]})
        self.assertEqual(old.draft, "")
        service = SimpleNamespace(chats={old.id:old}, save_chats=Mock())
        controller = ChatController(service)
        controller.generations[old.id] = object()
        controller.save_draft(old.id, "Unsent text")
        restored = Chat.from_dict(old.to_dict())
        self.assertEqual(restored.draft, "Unsent text")
        self.assertEqual(len(restored.messages), 1)
        self.assertEqual(restored.messages[0].content, "existing")
        with self.assertRaises(ValueError): controller.save_draft(old.id, "x"*32001)
        self.assertEqual(old.draft, "Unsent text")

    def test_clear_selection_preserves_pending_action_and_rejects_active_request(self):
        from olive.interaction.orchestrator import NaturalLanguageOrchestrator
        chat = Chat()
        services = SimpleNamespace(chats={chat.id:chat}, current_chat_id=chat.id,
            workspace_repo=SimpleNamespace(load_all=lambda: {}))
        n = NaturalLanguageOrchestrator(services, interpreter=Mock(), router=Mock())
        context = n.context(chat.id)
        context.entities["path"] = str(Path(self.temp.name)/"report.pdf")
        context.pending = {"id":"pending","entities":{"recipient":"person@example.test","message":"Unsent"}}
        n.active[chat.id] = object()
        with self.assertRaises(ValueError): n.clear_context(chat.id)
        self.assertEqual(n.presentation_context(chat.id)["file"], "report.pdf")
        n.active.clear()
        self.assertEqual(n.clear_context(chat.id), {"workspace":"","file":""})
        self.assertEqual(context.pending["entities"]["message"], "Unsent")
        self.assertEqual(context.pending["entities"]["recipient"], "person@example.test")


if __name__ == "__main__": unittest.main()
