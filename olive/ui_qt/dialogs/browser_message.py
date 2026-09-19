"""Choose visible draft fields; the service reads and confirms their exact values."""

from PySide6.QtWidgets import QDialog, QFormLayout, QComboBox, QLineEdit, QPushButton, QLabel


class BrowserMessageDialog(QDialog):
    def __init__(self, bridge, controls, parent=None):
        super().__init__(parent)
        self.bridge = bridge
        self.setWindowTitle("OLIVE — Review browser draft")
        self.resize(600, 400)
        layout = QFormLayout(self)
        self.fields = {}
        for key, title in (("destination", "Recipient field"), ("subject", "Subject field"),
                           ("body", "Message field"), ("send", "Send button")):
            combo = QComboBox()
            combo.addItem("Select the visible control", None)
            for control in controls:
                combo.addItem(control["name"] or control["type"] or "Unnamed control", control["id"])
            self.fields[key] = combo
            layout.addRow(title, combo)
        self.expected = QLineEdit()
        self.expected.setPlaceholderText("Control name that appears only after sending")
        layout.addRow("Sent-state evidence", self.expected)
        self.status = QLabel("OLIVE reads back the draft. A separate Send/Edit/Cancel preview is required before submission.")
        self.status.setWordWrap(True)
        layout.addRow(self.status)
        button = QPushButton("Read draft and request send review")
        button.clicked.connect(self.review)
        layout.addRow(button)

    def review(self):
        fields = {key: widget.currentData() for key, widget in self.fields.items()}
        if not all(fields.values()):
            self.status.setText("Select each draft field and its Send button")
            return
        self.bridge.call("desktop.browser_send", self.completed, fields=fields, expected=self.expected.text())

    def completed(self, result, error):
        self.status.setText(error or "Sent state verified")
