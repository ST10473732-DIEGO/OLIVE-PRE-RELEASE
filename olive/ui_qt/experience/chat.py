"""Content-driven Chat presentation retaining the existing conversation actions."""
import re
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QListWidget, QLineEdit, QPlainTextEdit, QPushButton, QComboBox, QScrollArea,
    QLabel, QMenu, QApplication)
from ..windows.chat import ChatWindow
from ..windows.base import FeatureWindow
from ..components.markdown import SafeMarkdown
from ..components.pending_draft import PendingDraftCard
from ..components.common import show_details


class ContentMarkdown(SafeMarkdown):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.document().documentLayout().documentSizeChanged.connect(self.fit_content)
        self.setMinimumHeight(28)

    def fit_content(self, *_):
        height = min(1600, max(28, int(self.document().size().height()) + 8))
        if self.height() != height:
            self.setFixedHeight(height)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fit_content()


class ConversationMessage(QWidget):
    def __init__(self, message, details, branch=None):
        super().__init__()
        self.setMaximumWidth(900)
        layout = QVBoxLayout(self); layout.setContentsMargins(4, 14, 4, 14); layout.setSpacing(6)
        row = QHBoxLayout()
        label = QLabel("You" if message["role"] == "user" else "OLIVE" if message["role"] == "assistant" else message["role"].title())
        label.setObjectName("eyebrow"); row.addWidget(label); row.addStretch()
        def action(text, callback):
            button = QPushButton(text); button.setObjectName("messageAction")
            button.clicked.connect(callback); row.addWidget(button)
        action("Copy", lambda: QApplication.clipboard().setText(message["content"]))
        if message.get("sources") or message.get("memory_ids") or message.get("grounding"):
            action("Sources", lambda: details(message))
        if branch: action("Alternative", branch)
        menu = QMenu(self)
        for index, block in enumerate(re.findall(r"```[^\n]*\n(.*?)```", message["content"], re.S), 1):
            menu.addAction(f"Copy code {index}", lambda checked=False, text=block: QApplication.clipboard().setText(text))
        if not menu.isEmpty():
            button = QPushButton("Code"); button.setMenu(menu); row.addWidget(button)
        layout.addLayout(row)
        self.body = ContentMarkdown(); self.body.setMarkdown(message["content"])
        layout.addWidget(self.body)


class ChatExperience(ChatWindow):
    message_widget_type = ConversationMessage
    stream_widget_type = ContentMarkdown

    def __init__(self, manager):
        FeatureWindow.__init__(self, manager, "chat")
        self.chat_id = None; self.chat_state = {}; self.projects = []
        self.streaming = None; self.visible_limit = 80; self.stream_text = ""; self.chat_list = []
        self._drafts = {}; self._submitting = False; self._selection = 0
        self._dirty_drafts = set()
        self._draft_saves = 0; self._exit_after_draft = False
        self.draft_timer = QTimer(self); self.draft_timer.setSingleShot(True); self.draft_timer.setInterval(600)
        self.draft_timer.timeout.connect(self.flush_drafts)
        self.setAcceptDrops(True)
        host = QWidget(); host.setObjectName("midnightChat")
        outer = QHBoxLayout(host); outer.setContentsMargins(0, 0, 0, 0)
        split = QSplitter(); outer.addWidget(split); self.setCentralWidget(host)
        side = QWidget(); left = QVBoxLayout(side); left.setContentsMargins(16, 24, 16, 16)
        title = QLabel("Conversations"); title.setObjectName("eyebrow"); left.addWidget(title)
        new = QPushButton("New conversation"); new.clicked.connect(self.new_chat); left.addWidget(new)
        self.search = QLineEdit(); self.search.setPlaceholderText("Find a conversation"); self.search.setAccessibleName("Search conversations")
        left.addWidget(self.search)
        self.conversations = QListWidget(); self.conversations.setAccessibleName("Conversations"); left.addWidget(self.conversations, 1)
        self.conversations.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.conversations.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.side = side
        split.addWidget(side)
        main = QWidget(); right = QVBoxLayout(main); right.setContentsMargins(28, 18, 28, 18); right.setSpacing(10)
        split.addWidget(main); split.setSizes([240, 900])
        row = QHBoxLayout()
        self.heading = QLabel("A place to think."); self.heading.setObjectName("title"); self.heading.setWordWrap(True); row.addWidget(self.heading, 1)
        self.models = QComboBox(); self.models.setAccessibleName("Chat model"); self.models.setMaximumWidth(220)
        self.models.setPlaceholderText("Model unavailable")
        self.models.activated.connect(self.change_model); row.addWidget(self.models)
        more = QPushButton("Conversation"); menu = QMenu(more)
        for text, callback in [("Rename", self.rename), ("Notes", self.notes), ("Summarize", self.summarize),
            ("Assign project", self.assign_project), ("Open Research", lambda: manager.open("research")),
            ("Developer: interaction details", self.interaction_details), ("Export", self.export), ("Delete", self.delete)]:
            menu.addAction(text, callback)
        more.setMenu(menu); row.addWidget(more); right.addLayout(row)
        self.area = QScrollArea(); self.area.setWidgetResizable(True)
        self.messages = QWidget(); self.message_layout = QVBoxLayout(self.messages)
        self.message_layout.setContentsMargins(12, 12, 12, 12); self.message_layout.addStretch()
        self.area.setWidget(self.messages); right.addWidget(self.area, 1)
        self.attachments = QLabel(); self.attachments.setWordWrap(True); right.addWidget(self.attachments)
        self.attachment_chips = QWidget(); self.chips_layout = QHBoxLayout(self.attachment_chips)
        self.chips_layout.setContentsMargins(0,0,0,0); right.addWidget(self.attachment_chips)
        self.context_button = QPushButton("Selected context"); self.context_button.clicked.connect(manager.experience.showContext)
        right.addWidget(self.context_button)
        self.activity_label = QLabel(); self.activity_label.setObjectName("quiet")
        self.activity_label.setTextFormat(Qt.TextFormat.PlainText); self.activity_label.setWordWrap(True)
        right.addWidget(self.activity_label); self.activity_label.hide()
        self.pending_draft = PendingDraftCard(self); right.addWidget(self.pending_draft)
        self.composer = QPlainTextEdit(); self.composer.setAccessibleName("Message composer")
        self.composer.setPlaceholderText("Ask, explore, or pick up where you left off…")
        self.composer.setFixedHeight(80); right.addWidget(self.composer)
        buttons = QHBoxLayout()
        attach = QPushButton("Attach"); attachments = QMenu(attach)
        attachments.addAction("Attach file or image", lambda: self.attach())
        attachments.addAction("Add knowledge source", lambda: self.attach(True))
        attachments.addAction("Remove image", self.remove_image); attach.setMenu(attachments); buttons.addWidget(attach)
        regenerate = QPushButton("Regenerate"); regenerate.clicked.connect(self.regenerate); buttons.addWidget(regenerate)
        buttons.addStretch()
        hint = QLabel("Ctrl + Enter to send"); hint.setObjectName("quiet"); buttons.addWidget(hint)
        self.stop_button = QPushButton("Stop"); self.stop_button.clicked.connect(self.stop); buttons.addWidget(self.stop_button)
        self.send_button = QPushButton("Send"); self.send_button.setObjectName("primary"); self.send_button.clicked.connect(self.send); buttons.addWidget(self.send_button)
        right.addLayout(buttons)
        self.search.textChanged.connect(self.filter_chats)
        self.conversations.currentItemChanged.connect(self.choose_chat)
        self.composer.textChanged.connect(self.remember_draft)
        for shortcut, callback in [("Ctrl+N", self.new_chat), ("Ctrl+Return", self.send)]:
            action = QAction(self); action.setShortcut(QKeySequence(shortcut)); action.triggered.connect(callback); self.addAction(action)
        self.statusBar().hide()
        manager.experience.changed.connect(self.update_context)
        self.update_context()

    def update_context(self):
        text = self.manager.experience.contextLabel
        self.context_button.setText(text or "Selected context")
        self.context_button.setVisible(bool(text))

    def on_event(self, topic, value):
        super().on_event(topic, value)
        if not hasattr(self, "activity_label"): return
        if topic == "interaction_activity" and value.get("chat_id") == self.chat_id:
            self.activity_label.setText(value.get("message", "")); self.activity_label.show()
        elif topic == "chat" and value.get("id") == self.chat_id and not value.get("generating"):
            self.activity_label.hide()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "side"):
            self.side.setVisible(self.width() >= 1050)

    def delete(self):
        self.flush_drafts()
        super().delete()

    def remember_draft(self):
        lines = max(1, self.composer.document().blockCount())
        self.composer.setFixedHeight(min(140, max(80, lines * self.composer.fontMetrics().lineSpacing() + 28)))
        if self.chat_id:
            self._drafts[self.chat_id] = self.composer.toPlainText()
            self._dirty_drafts.add(self.chat_id); self.draft_timer.start()

    def flush_drafts(self):
        self.draft_timer.stop()
        for identity in tuple(self._dirty_drafts):
            text = self._drafts[identity]
            self._dirty_drafts.discard(identity)
            self._draft_saves += 1
            def saved(value, error, identity=identity):
                self._draft_saves -= 1
                if error:
                    self._dirty_drafts.add(identity)
                    self.heading.setText("Draft could not be saved. Your text is still open.")
                    self._exit_after_draft = False
                elif self._exit_after_draft and not self._dirty_drafts and not self._draft_saves:
                    self._exit_after_draft = False
                    QTimer.singleShot(0, self.manager.exit)
            self.call("chat.save_draft", saved, chat_id=identity, text=text)

    def can_close(self, exiting=False):
        if self._dirty_drafts or self._draft_saves:
            self._exit_after_draft = exiting
            self.flush_drafts()
            return False
        self.flush_drafts()
        return True

    def select_chat(self, identity):
        self._selection += 1
        selection = self._selection
        self.call("chat.select", lambda value, error: self.render(value, error) if selection == self._selection else None, chat_id=identity)

    def choose_chat(self, item, previous=None):
        if item: self.select_chat(item.data(Qt.ItemDataRole.UserRole))

    def render(self, value, error=""):
        if not value: return
        changed = self.chat_id != value["id"]
        super().render(value, error)
        if changed:
            self.composer.blockSignals(True)
            self.composer.setPlainText(self._drafts.get(self.chat_id, value.get("draft", "")))
            self.composer.blockSignals(False)
            self.manager.experience.refresh()
        self.heading.setText(value["title"] if value["messages"] else "A place to think.")
        self.stop_button.setVisible(bool(value.get("generating") or self._submitting))
        self.send_button.setEnabled(not self._submitting and not value.get("generating"))
        self.attachments.hide()
        while self.chips_layout.count():
            item = self.chips_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        attachments = [(d["name"], "Indexed document" if d.get("indexed") else "Document awaiting indexing") for d in value.get("documents",[])]
        attachments += [(i["name"], "Image attached") for i in value.get("images",[])]
        for name, status in attachments[:8]:
            button = QPushButton(name); button.setToolTip(status)
            button.clicked.connect(lambda checked=False, name=name, status=status: show_details(self, "Attachment", {"Name":name,"Status":status}))
            self.chips_layout.addWidget(button)
        if len(attachments)>8:self.chips_layout.addWidget(QLabel(f"+{len(attachments)-8} more"))
        self.chips_layout.addStretch()
        self.attachment_chips.setVisible(bool(attachments))
        if not value["messages"] and not value.get("generating"):
            empty = QLabel("Bring a question, a document, or an idea.\nOLIVE can help you think it through and take the next step.")
            empty.setObjectName("quiet"); empty.setWordWrap(True)
            empty.setContentsMargins(8, 36, 8, 24); self.message_layout.insertWidget(0, empty)

    def send(self):
        if self._submitting or self.chat_state.get("generating") or not self.chat_id: return
        text = self.composer.toPlainText().strip()
        if not text: return
        if len(text) > 4000:
            self.heading.setText("Please keep this request to 4,000 characters."); return
        self._submitting = True; self.send_button.setEnabled(False); self.stop_button.show()
        identity = self.chat_id
        self.composer.clear()
        def done(value, error):
            self._submitting = False
            if self.chat_id != identity: return
            if error:
                self.composer.setPlainText(text); self.heading.setText(error)
            if value: self.render(value)
            self.send_button.setEnabled(not self.chat_state.get("generating"))
            self.stop_button.setVisible(bool(self.chat_state.get("generating")))
        self.call("interaction.submit", done, chat_id=identity, text=text)
