"""Human-readable unsent draft; final submission still uses consequence review."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGroupBox, QVBoxLayout, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QInputDialog


class PendingDraftCard(QGroupBox):
    def __init__(self, owner):
        super().__init__("Unsent message")
        self.owner, self.pending = owner, None
        layout = QVBoxLayout(self)
        self.destination = QLabel()
        self.destination.setTextFormat(Qt.TextFormat.PlainText)
        self.destination.setWordWrap(True)
        layout.addWidget(self.destination)
        self.body = QPlainTextEdit()
        self.body.setReadOnly(True)
        self.body.setAccessibleName("Pending message text")
        self.body.setMaximumHeight(100)
        layout.addWidget(self.body)
        row = QHBoxLayout()
        self.action_buttons = []
        for text, callback in (("Review Send", self.send), ("Edit", self.edit), ("Cancel draft", self.cancel)):
            button = QPushButton(text)
            button.clicked.connect(callback)
            row.addWidget(button)
            if text != "Cancel draft":
                self.action_buttons.append(button)
        layout.addLayout(row)
        self.hide()

    def render(self, pending):
        self.pending = pending
        self.setVisible(bool(pending and pending.get("state") != "sent"))
        if not pending:
            return
        fields = pending.get("entities", {})
        uncertain = bool(pending.get("submission_uncertain"))
        self.setTitle("Check message delivery in the application" if uncertain else "Unsent message")
        for button in self.action_buttons:
            button.setEnabled(not uncertain)
        self.destination.setText("\n".join(f"{key.title()}: {fields[key]}" for key in
            ("application", "server", "channel", "recipient", "subject") if fields.get(key)))
        self.body.setPlainText(fields.get("message", ""))

    def send(self):
        # This is a request, not approval. Existing deterministic consequence review remains mandatory.
        self.owner.call("interaction.submit", text="Send the pending message.", chat_id=self.owner.chat_id)

    def edit(self):
        text, accepted = QInputDialog.getMultiLineText(self, "Edit unsent message", "Message", self.body.toPlainText())
        if accepted:
            self.owner.call("interaction.edit_draft", chat_id=self.owner.chat_id, message=text)

    def cancel(self):
        self.owner.call("interaction.edit_draft", chat_id=self.owner.chat_id, cancel=True)
