import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import QObject, Signal, QThread, Qt, QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtTest import QTest

from olive.ui_qt.feature_registry import default_registry
from olive.ui_qt.window_manager import WindowManager
from olive.ui_qt.window_state import WindowStateStore
from olive.ui_qt.runtime import BackendBridge
from olive.ui_qt.studio.native_editor import NativeEditor
from olive.ui_qt.dialogs.confirmation import ConfirmationDialog
from olive.agent.confirmation_service import ConfirmationRequest

APP = QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)


class FakeBridge(QObject):
    event = Signal(str, object)
    confirmation = Signal(object)
    stopped = Signal()

    def __init__(self):
        super().__init__()
        self.calls = []

    def call(self, operation, callback=None, **arguments):
        self.calls.append((operation, arguments, callback))

    def answer(self, *args):
        self.answer_value = args

    def stop_control(self):
        self.call("desktop.stop")

    def shutdown(self):
        self.stopped.emit()


class QtWindowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.bridge = FakeBridge()
        self.manager = WindowManager(self.bridge, default_registry(), Path(self.temp.name) / "ui.json")

    def tearDown(self):
        self.manager.exiting = True
        for window in self.manager.windows.values():
            if hasattr(window, "documents"):
                for doc in window.documents.values():
                    doc["editor"].document().setModified(False)
            window.close()
            window.deleteLater()
        for window in self.manager.popouts.values():
            window.close()
            window.deleteLater()
        if self.manager.main:
            self.manager.main.close()
            self.manager.main.deleteLater()
        self.manager.deleteLater()
        self.bridge.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        APP.processEvents()

    def test_home_registry_and_lazy_singleton_windows(self):
        home = self.manager.open("home")
        self.assertEqual(len(home.cards), 8)
        self.assertEqual(list(self.manager.windows), ["home"])
        chat = self.manager.open("chat")
        self.assertIs(chat, self.manager.open("chat"))

    def test_home_and_chat_use_shared_natural_language_front_door(self):
        home = self.manager.open("home")
        shell = self.manager.main
        home.composer.setText("Bring my application up")
        home.submit_request()
        self.assertIs(self.manager.main, shell)
        chat = self.manager.windows["chat"]
        self.assertIs(shell.stack.currentWidget(), chat)
        self.assertEqual(self.bridge.calls[-1][:2], ("interaction.submit", {"text": "Bring my application up"}))
        chat.chat_id = "conversation"
        chat.composer.setPlainText("Actually use the other file")
        chat.send()
        self.assertEqual(self.bridge.calls[-1][:2], ("interaction.submit", {
            "chat_id": "conversation", "text": "Actually use the other file"}))
        chat.stop()
        self.assertEqual(self.bridge.calls[-1][:2], ("interaction.cancel", {"chat_id": "conversation"}))
        self.assertIs(chat.bridge, home.bridge)
        chat.close()
        self.assertIs(chat, self.manager.open("chat"))

    def test_navigation_uses_one_primary_window_and_no_refresh_duplicates(self):
        home = self.manager.open("home")
        shell = self.manager.main
        self.assertIs(shell.stack.currentWidget(), home)
        chat = self.manager.open("chat")
        self.assertIs(chat.window(), shell)
        self.assertFalse(chat.isWindow())
        calls = len(self.bridge.calls)
        self.manager.open("chat")
        self.assertEqual(len(self.bridge.calls), calls)
        self.assertEqual(self.manager.navigation.history, ["home", "chat"])
        self.manager.navigation.back()
        self.assertIs(shell.stack.currentWidget(), home)
        self.manager.navigation.forward()
        self.assertIs(shell.stack.currentWidget(), chat)
        self.manager.navigation.back()
        self.manager.open("studio")
        self.assertEqual(self.manager.navigation.history, ["home", "studio"])

    def test_workspace_switch_preserves_editor_draft_and_background_updates(self):
        studio = self.manager.open("studio")
        studio.workspace_id = "workspace"
        studio.file_loaded("workspace", "a.py", 1, {"text": "one\ntwo", "loaded_hash": "hash", "saved_text": "one\ntwo"}, "")
        editor = studio.tabs.currentWidget()
        editor.go_to_line(2, 2)
        editor.insertPlainText("draft")
        cursor = editor.cursor_position()
        layout = bytes(studio.saveState())
        chat = self.manager.open("chat")
        chat.composer.setPlainText("Unsent draft")
        self.bridge.event.emit("terminal", {"workspace_id": "workspace", "stdout": "background output", "stderr": "", "exit_code": 0})
        self.manager.open("home")
        self.assertIs(self.manager.open("studio"), studio)
        self.assertIs(studio.tabs.currentWidget(), editor)
        self.assertEqual(editor.cursor_position(), cursor)
        self.assertTrue(editor.document().isModified())
        self.assertEqual(bytes(studio.saveState()), layout)
        self.assertIn("background output", studio.terminal_output.toPlainText())
        self.assertEqual(self.manager.open("chat").composer.toPlainText(), "Unsent draft")

    def test_explicit_popout_moves_same_workspace_and_returns_without_loss(self):
        chat = self.manager.open("chat")
        chat.composer.setPlainText("Keep this draft")
        popout = self.manager.popout("chat")
        self.assertIs(chat.window(), popout)
        self.assertIs(popout.centralWidget(), chat)
        self.assertIs(self.manager.popout("chat"), popout)
        popout.close()
        self.assertFalse(self.manager.popouts)
        self.assertIs(chat.window(), self.manager.main)
        self.assertEqual(chat.composer.toPlainText(), "Keep this draft")

    def test_shell_stop_remains_reachable_from_another_workspace(self):
        self.manager.open("desktop")
        self.manager.open("home")
        self.bridge.event.emit("desktop", {"settings": {"enabled": True}, "stopped": False, "active": True, "session": {}, "observation": {}})
        self.assertTrue(self.manager.main.stop_action.isVisible())
        self.manager.main.stop_action.trigger()
        self.assertEqual(self.bridge.calls[-1][0], "desktop.stop")

    def test_main_close_checks_dirty_inactive_studio(self):
        studio = self.manager.open("studio")
        studio.file_loaded("workspace", "a.py", 1, {"text": "one", "loaded_hash": "hash", "saved_text": "one"}, "")
        studio.tabs.currentWidget().insertPlainText("unsaved")
        self.manager.open("home")
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Cancel):
            self.manager.main.close()
        self.assertFalse(self.manager.exiting)
        self.assertTrue(self.manager.main.isVisible())
        self.assertTrue(studio.tabs.currentWidget().document().isModified())

    def test_global_shortcut_and_collapsed_navigation(self):
        self.manager.open("home")
        self.manager.main.activateWindow()
        APP.processEvents()
        QTest.keyClick(self.manager.main, Qt.Key.Key_4, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(self.manager.navigation.current, "studio")
        self.manager.main.toggle_rail()
        self.assertEqual(self.manager.main.rail.width(), 52)
        self.assertEqual(self.manager.main.items["studio"].toolTip(), "Studio")

    def test_desktop_callback_contract_and_error_state(self):
        from olive.desktop.settings import DEFAULTS
        window = self.manager.open("desktop")
        callback = self.bridge.calls[-1][2]
        callback({"settings": DEFAULTS, "stopped": False, "session": None, "observation": {}}, "")
        self.assertFalse(window.enabled.isChecked())
        callback(None, "Focus changed")
        self.assertEqual(window.state.text(), "Focus changed")

    def test_every_feature_constructs_with_shared_bridge(self):
        for feature in self.manager.registry.list():
            window = self.manager.open(feature.id)
            self.assertIs(window.bridge, self.bridge)
        self.assertEqual(len(self.manager.windows), 11)

    def test_research_reopens_evidence_without_starting_network(self):
        from olive.research.models import ResearchSession, ResearchSource, ResearchEvidence
        window = self.manager.open("research")
        session = ResearchSession("Current embeddings documentation")
        source = ResearchSource("https://docs.example.com/", "Documentation", status="read")
        session.sources.append(source)
        session.evidence.append(ResearchEvidence(source.id, session.question, "Embeddings", "Embeddings represent text.", 0, 26))
        window.render(session.to_dict())
        window.sources.selectRow(0)
        self.assertIn("Embeddings represent text", window.evidence.toPlainText())
        window.close()
        self.assertIs(window, self.manager.open("research"))
        self.assertEqual(window.session["id"], session.id)
        self.assertFalse(any(operation == "research.start" for operation, _, _ in self.bridge.calls))

    def test_studio_research_handoff_is_bounded_and_requires_start(self):
        studio = self.manager.open("studio")
        studio.request.setPlainText("compiler error " * 500)
        studio.research()
        research = self.manager.windows["research"]
        self.assertLessEqual(len(research.context["error"]), 4000)
        self.assertLessEqual(len(research.question.text()), 4000)
        self.assertFalse(any(operation == "research.start" for operation, _, _ in self.bridge.calls))

    def test_web_learning_scope_invalidates_after_input_changes(self):
        from olive.ui_qt.dialogs.web_knowledge import WebKnowledgeDialog
        dialog = WebKnowledgeDialog(self.manager)
        dialog.reviewed({"urls": ["https://example.com/"]}, "")
        dialog.urls.setPlainText("https://other.example.com/")
        dialog.learn()
        self.assertEqual(dialog.scope_urls, [])
        self.assertFalse(any(operation == "research.learn_urls" for operation, _, _ in self.bridge.calls))
        dialog.deleteLater()

    def test_corrupted_state_recovers_and_offscreen_position_is_safe(self):
        path = Path(self.temp.name) / "broken.json"
        path.write_text("{not json", encoding="utf-8")
        store = WindowStateStore(path)
        self.assertEqual(store.get("home"), {})
        self.manager.state.values = {"home": {"geometry": "not base64", "docks": 123}}
        self.assertIsNotNone(self.manager.open("home"))
        self.manager.save_window(self.manager.windows["home"])
        self.assertIn("geometry", WindowStateStore(self.manager.state.path).get("home"))

    def test_confirmation_denial_cancel_and_approval(self):
        request = ConfirmationRequest(
            "task", "filesystem.write", "Write approved file", "medium", ["fixture.py"]
        )
        dialog = ConfirmationDialog(request)
        self.assertFalse(dialog.response.approved)
        dialog.cancel_task()
        self.assertTrue(dialog.response.cancel_task)
        dialog = ConfirmationDialog(request)
        dialog.approve()
        self.assertTrue(dialog.response.approved)

    def test_editor_adapter_cursor_dirty_and_line_numbers(self):
        editor = NativeEditor()
        editor.set_text("one\ntwo\n")
        self.assertFalse(editor.document().isModified())
        editor.go_to_line(2, 2)
        self.assertEqual(editor.cursor_position(), (2, 2))
        editor.insertPlainText("X")
        self.assertTrue(editor.document().isModified())
        self.assertGreater(editor.line_number_width(), 10)
        editor.set_language("python")
        editor.set_diagnostics([{"line": 2}])
        self.assertEqual(editor.save_state()["line"], 2)
        editor.set_read_only(True)
        self.assertTrue(editor.isReadOnly())
        original = editor.get_text()
        QTest.keyClick(editor, Qt.Key.Key_Return)
        QTest.keyClick(editor, Qt.Key.Key_Tab)
        self.assertEqual(editor.get_text(), original)
        editor.deleteLater()

    def test_editor_auto_indent_and_find(self):
        editor = NativeEditor()
        editor.set_text("if True:")
        editor.moveCursor(editor.textCursor().MoveOperation.End)
        QTest.keyClick(editor, Qt.Key.Key_Return)
        self.assertEqual(editor.get_text(), "if True:\n    ")
        editor.deleteLater()

    def test_studio_dirty_close_cancel_and_discard(self):
        studio = self.manager.open("studio")
        studio.file_loaded(
            "workspace", "a.py", 1, {"text": "one", "loaded_hash": "hash", "saved_text": "one"}, ""
        )
        editor = studio.tabs.currentWidget()
        editor.insertPlainText("changed")
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Cancel):
            studio.close_tab(0)
        self.assertEqual(studio.tabs.count(), 1)
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Discard):
            studio.close_tab(0)
        self.assertEqual(studio.tabs.count(), 0)

    def test_studio_save_uses_controller_hash_boundary(self):
        studio = self.manager.open("studio")
        studio.file_loaded(
            "workspace", "a.py", 1, {"text": "one", "loaded_hash": "hash", "saved_text": "one"}, ""
        )
        studio.tabs.currentWidget().insertPlainText("two")
        studio.save()
        operation, arguments, callback = self.bridge.calls[-1]
        self.assertEqual(operation, "studio.access")
        self.assertEqual(arguments["action"], "save")
        self.assertEqual(arguments["expected_hash"], "hash")
        callback({"loaded_hash": "new", "saved_text": studio.tabs.currentWidget().get_text()}, "")
        self.assertFalse(studio.tabs.currentWidget().document().isModified())

    def test_dock_reset_and_output_test_problem_events(self):
        studio = self.manager.open("studio")
        studio.workspace_id = "workspace"
        studio.output_dock.hide()
        studio.reset_layout()
        self.assertFalse(studio.output_dock.isHidden())
        self.bridge.event.emit(
            "terminal", {"workspace_id": "workspace", "stdout": "hello", "stderr": "", "exit_code": 0}
        )
        self.assertIn("hello", studio.terminal_output.toPlainText())
        self.bridge.event.emit(
            "tests", {"workspace_id": "workspace", "items": [{"name": "test_a", "state": "passed"}]}
        )
        self.assertEqual(studio.tests.rowCount(), 1)
        self.bridge.event.emit(
            "problems",
            {"workspace_id": "workspace", "items": [{"file": "a.py", "line": 3, "message": "error"}]},
        )
        studio.problems.selectRow(0)
        studio.open_problem()
        self.assertEqual(self.bridge.calls[-1][1]["path"], "a.py")

    def test_notifications_and_palette(self):
        from olive.ui_qt.commands import CommandPalette

        home = self.manager.open("home")
        self.bridge.event.emit("notification", {"kind": "warning", "message": "Test status"})
        self.assertEqual(home.statusBar().currentMessage(), "Test status")
        palette = CommandPalette(self.manager, home)
        palette.filter("Open Studio")
        self.assertEqual(palette.results.count(), 1)
        palette.activate()
        self.assertIn("studio", self.manager.windows)

    def test_settings_have_all_categories(self):
        settings = self.manager.open("settings")
        self.assertEqual(settings.tabs.count(), 16)
        self.assertIn("rag_semantic_weight", settings.controls)
        self.assertIn("ocr_executable", settings.controls)
        self.assertIn("system_prompt", settings.controls)


class RuntimeTests(unittest.TestCase):
    def test_failed_initialization_can_still_close(self):
        def broken_factory(emit, confirm):
            raise RuntimeError("Fixture initialization failure")

        bridge = BackendBridge(broken_factory)
        bridge.start()
        deadline = time.monotonic() + 5
        while bridge.worker.isRunning() and time.monotonic() < deadline:
            APP.processEvents()
            time.sleep(0.01)
        self.assertFalse(bridge.worker.isRunning())
        closed = []
        bridge.stopped.connect(lambda: closed.append(True))
        bridge.shutdown()
        self.assertTrue(closed)

    def test_all_progress_topics_deliver_on_gui_thread_and_shutdown(self):
        class Services:
            def __init__(self, emit, confirm):
                self.emit = emit

            async def initialize(self):
                for topic in ("chat_stream", "agent", "terminal", "indexing", "research"):
                    self.emit(topic, {"worker_thread": QThread.currentThread() is not APP.thread()})

            async def dispatch(self, operation, arguments):
                return {"shared": True}

            async def shutdown(self):
                return None

        bridge = BackendBridge(Services)
        received = []
        results = []

        class Receiver(QObject):
            from PySide6.QtCore import Slot

            @Slot(str, object)
            def receive(self, topic, value):
                received.append((topic, QThread.currentThread() == APP.thread(), value))

        receiver = Receiver()
        bridge.event.connect(receiver.receive)
        bridge.start()
        bridge.call("data.example", lambda v, e: results.append((v, QThread.currentThread() == APP.thread())))
        deadline = time.monotonic() + 5
        while (len(received) < 5 or not results) and time.monotonic() < deadline:
            APP.processEvents()
            time.sleep(0.01)
        try:
            self.assertEqual(len(received), 5)
            self.assertTrue(all(on_gui and value["worker_thread"] for _, on_gui, value in received))
            self.assertTrue(results[0][1])
        finally:
            bridge.shutdown()
            deadline = time.monotonic() + 5
            while bridge.worker.isRunning() and time.monotonic() < deadline:
                APP.processEvents()
                time.sleep(0.01)
            self.assertFalse(bridge.worker.isRunning())


if __name__ == "__main__":
    unittest.main()
