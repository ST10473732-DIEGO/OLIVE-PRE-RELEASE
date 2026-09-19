from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence, QTextCursor
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QListWidget,
    QListWidgetItem,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QComboBox,
    QScrollArea,
    QLabel,
    QFileDialog,
    QInputDialog,
    QMessageBox,
    QMenu,
)
from .base import FeatureWindow
from ..components.markdown import MessageWidget, SafeMarkdown
from ..components.common import show_details
from ..components.pending_draft import PendingDraftCard


class ChatWindow(FeatureWindow):
    message_widget_type = MessageWidget
    stream_widget_type = SafeMarkdown
    def interaction_details(self):
        self.call("interaction.inspect", lambda value, error: show_details(
            self, "Developer interaction details", value) if value is not None and not error else None,
            chat_id=self.chat_id)

    def __init__(self, manager):
        super().__init__(manager, "chat")
        self.chat_id = None
        self.chat_state = {}
        self.projects = []
        self.streaming = None
        self.visible_limit = 80
        self.stream_text = ""
        self.setAcceptDrops(True)
        outer = self.page("Chat")
        split = QSplitter()
        outer.addWidget(split, 1)
        side = QWidget()
        left = QVBoxLayout(side)
        new = QPushButton("New chat")
        new.setObjectName("primary")
        new.clicked.connect(self.new_chat)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search conversations")
        self.conversations = QListWidget()
        left.addWidget(new)
        left.addWidget(self.search)
        left.addWidget(self.conversations)
        split.addWidget(side)
        main = QWidget()
        right = QVBoxLayout(main)
        split.addWidget(main)
        split.setSizes([240, 800])
        row = QHBoxLayout()
        self.models = QComboBox()
        self.models.setMinimumWidth(220)
        self.models.setAccessibleName("Chat model")
        self.models.activated.connect(self.change_model)
        row.addWidget(self.models, 1)
        more = QPushButton("Conversation")
        menu = QMenu(more)
        for title, callback in [
            ("Rename", self.rename),
            ("Notes", self.notes),
            ("Summarize", self.summarize),
            ("Assign project", self.assign_project),
            ("Open Research", lambda: self.manager.open("research")),
            ("Developer: interaction details", self.interaction_details),
            ("Export", self.export),
            ("Delete", self.delete),
        ]:
            menu.addAction(title, callback)
        more.setMenu(menu)
        row.addWidget(more)
        right.addLayout(row)
        self.area = QScrollArea()
        self.area.setWidgetResizable(True)
        self.messages = QWidget()
        self.message_layout = QVBoxLayout(self.messages)
        self.message_layout.addStretch()
        self.area.setWidget(self.messages)
        right.addWidget(self.area, 1)
        self.attachments = QLabel()
        self.attachments.setWordWrap(True)
        right.addWidget(self.attachments)
        self.pending_draft = PendingDraftCard(self)
        right.addWidget(self.pending_draft)
        self.composer = QPlainTextEdit()
        self.composer.setPlaceholderText("Message OLIVE…  Ctrl+Enter to send")
        self.composer.setMaximumHeight(140)
        self.composer.setAccessibleName("Message composer")
        right.addWidget(self.composer)
        buttons = QHBoxLayout()
        for title, callback in [
            ("Attach", self.attach),
            ("Add knowledge", lambda: self.attach(True)),
            ("Remove image", self.remove_image),
            ("Regenerate", self.regenerate),
            ("Stop", self.stop),
        ]:
            button = QPushButton(title)
            button.clicked.connect(callback)
            buttons.addWidget(button)
        self.send_button = QPushButton("Send")
        self.send_button.setObjectName("primary")
        self.send_button.clicked.connect(self.send)
        buttons.addWidget(self.send_button)
        right.addLayout(buttons)
        self.search.textChanged.connect(self.filter_chats)
        self.conversations.currentItemChanged.connect(self.choose_chat)
        action = QAction(self)
        action.setShortcut(QKeySequence("Ctrl+N"))
        action.triggered.connect(self.new_chat)
        self.addAction(action)
        action = QAction(self)
        action.setShortcut(QKeySequence("Ctrl+Return"))
        action.triggered.connect(self.send)
        self.addAction(action)
        self.chat_list = []

    def refresh(self):
        self.call("chat.list", lambda v, e: self.render_list(v) if v is not None else None)
        self.call("chat.get", self.render)
        self.call("data.models", lambda v, e: self.render_models(v) if v is not None else None)
        self.call("data.projects", lambda v, e: setattr(self, "projects", v or []))

    def render_list(self, values):
        self.chat_list = values
        self.filter_chats(self.search.text())

    def filter_chats(self, text):
        self.conversations.blockSignals(True)
        self.conversations.clear()
        for value in self.chat_list:
            if text.casefold() in value["title"].casefold():
                item = QListWidgetItem(value["title"])
                item.setData(Qt.ItemDataRole.UserRole, value["id"])
                self.conversations.addItem(item)
                if value["id"] == self.chat_id:
                    self.conversations.setCurrentItem(item)
        self.conversations.blockSignals(False)

    def choose_chat(self, item, previous=None):
        if item:
            self.call("chat.select", self.render, chat_id=item.data(Qt.ItemDataRole.UserRole))

    def render_models(self, values):
        self.models.blockSignals(True)
        self.models.clear()
        for value in values:
            self.models.addItem(value["alias"] or value["name"], value["name"])
        self.models.setCurrentIndex(self.models.findData(self.chat_state.get("model")))
        self.models.blockSignals(False)

    def render(self, value, error=""):
        if not value:
            return
        if self.chat_id != value["id"]:
            self.visible_limit = 80
        self.chat_id = value["id"]
        self.chat_state = value
        self.pending_draft.render(value.get("pending_draft"))
        self.models.setCurrentIndex(self.models.findData(value["model"]))
        while self.message_layout.count() > 1:
            item = self.message_layout.takeAt(0)
            item.widget().deleteLater()
        self.streaming = None
        start = max(0, len(value["messages"]) - self.visible_limit)
        if start:
            earlier = QPushButton(f"Load earlier messages ({start} hidden)")
            earlier.clicked.connect(self.load_earlier)
            self.message_layout.insertWidget(0, earlier)
        for index, message in enumerate(value["messages"][start:], start):
            user_index = index - 1
            branch = (
                (
                    lambda checked=False, i=user_index: self.call(
                        "chat.branch", self.render, chat_id=self.chat_id, user_index=i
                    )
                )
                if len(value["response_branches"].get(str(user_index), [])) > 1
                else None
            )
            widget = self.message_widget_type(
                message,
                lambda m: show_details(
                    self, "Response provenance", {k: m.get(k) for k in ("sources", "memory_ids", "grounding")}
                ),
                branch,
            )
            self.message_layout.insertWidget(self.message_layout.count() - 1, widget)
        if value.get("generating"):
            self.streaming = self.stream_widget_type()
            self.streaming.setPlainText("Thinking…")
            if self.stream_widget_type is SafeMarkdown:
                self.streaming.setMinimumHeight(150)
            self.stream_text = ""
            self.message_layout.insertWidget(self.message_layout.count() - 1, self.streaming)
        self.send_button.setEnabled(not value.get("generating"))
        self.attachments.setText(
            " · ".join([d["name"] for d in value["documents"]] + [i["name"] for i in value.get("images", [])])
        )
        self.filter_chats(self.search.text())

    def on_event(self, topic, value):
        super().on_event(topic, value)
        if topic == "chats":
            self.render_list(value)
        elif topic == "interaction_activity" and value["chat_id"] == self.chat_id:
            self.statusBar().showMessage(value["message"])
        elif topic == "models":
            self.render_models(value)
        elif topic == "chat" and value["id"] == self.chat_id:
            self.render(value)
        elif topic == "chat_stream" and value["chat_id"] == self.chat_id and self.streaming:
            # Update only the active response, never rebuild previous messages per token.
            text = value["text"]
            if not self.stream_text:
                self.streaming.clear()
            cursor = self.streaming.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            cursor.insertText(text[len(self.stream_text) :])
            self.streaming.setTextCursor(cursor)
            self.stream_text = text

    def load_earlier(self):
        self.visible_limit += 80
        self.render(self.chat_state)

    def new_chat(self):
        self.call("chat.new", self.render)

    def send(self):
        if self.chat_id and self.composer.toPlainText().strip():
            text = self.composer.toPlainText()
            self.composer.clear()
            self.call("interaction.submit", chat_id=self.chat_id, text=text)

    def stop(self):
        if self.chat_id:
            self.call("interaction.cancel", chat_id=self.chat_id)

    def regenerate(self):
        if self.chat_id:
            self.call("chat.send", chat_id=self.chat_id, regenerate=True)

    def change_model(self):
        if self.chat_id:
            self.call("chat.update", self.render, chat_id=self.chat_id, model=self.models.currentData())

    def rename(self):
        value, ok = QInputDialog.getText(
            self, "Rename conversation", "Title", text=self.chat_state.get("title", "")
        )
        if ok:
            self.call("chat.update", self.render, chat_id=self.chat_id, title=value)

    def notes(self):
        value, ok = QInputDialog.getMultiLineText(
            self, "Conversation notes", "Context to remember", self.chat_state.get("notes", "")
        )
        if ok:
            self.call("chat.update", self.render, chat_id=self.chat_id, notes=value)

    def summarize(self):
        self.call(
            "chat.summarize",
            lambda v, e: show_details(self, "Conversation summary", v) if v else None,
            chat_id=self.chat_id,
        )

    def assign_project(self):
        names = ["None"] + [p["title"] for p in self.projects]
        value, ok = QInputDialog.getItem(self, "Project", "Associate conversation", names, editable=False)
        if ok:
            self.call(
                "chat.update",
                self.render,
                chat_id=self.chat_id,
                project_id=None if value == "None" else self.projects[names.index(value) - 1]["id"],
            )

    def export(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export conversation", "conversation.md", "Markdown (*.md);;JSON (*.json)"
        )
        if path:
            self.call("data.export", path=path, chat_id=self.chat_id)

    def delete(self):
        if (
            QMessageBox.question(
                self, "Delete conversation", "Delete this conversation and its document indexes?"
            )
            == QMessageBox.StandardButton.Yes
        ):
            self.call("chat.delete", self.render, chat_id=self.chat_id)

    def attach(self, permanent=False):
        paths, _ = QFileDialog.getOpenFileNames(self, "Add local files")
        if paths:
            self.call("knowledge.attach", chat_id=self.chat_id, paths=paths, permanent=bool(permanent))

    def remove_image(self):
        values = self.chat_state.get("images", [])
        if values:
            name, ok = QInputDialog.getItem(
                self, "Remove image", "Attachment", [v["name"] for v in values], editable=False
            )
            if ok:
                self.call(
                    "chat.remove_image",
                    self.render,
                    chat_id=self.chat_id,
                    index=[v["name"] for v in values].index(name),
                )

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and all(u.isLocalFile() for u in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        if self.chat_id:
            self.call(
                "knowledge.attach",
                chat_id=self.chat_id,
                paths=[u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()],
            )
