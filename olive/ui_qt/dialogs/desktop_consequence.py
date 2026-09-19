"""Select visible action evidence before the authoritative consequence preview."""

from PySide6.QtWidgets import QDialog, QVBoxLayout, QFormLayout, QComboBox, QLineEdit, QPushButton, QLabel, QWidget
from ...desktop.action_preview import REQUIRED_FIELDS


class DesktopConsequenceDialog(QDialog):
    def __init__(self, bridge, controls, target, parent=None):
        super().__init__(parent)
        self.bridge, self.controls, self.target = bridge, controls, target
        self.setWindowTitle("OLIVE — Consequential action")
        self.resize(620, 500)
        layout = QVBoxLayout(self)
        self.kind = QComboBox()
        for label, permission in (("Install free software", "software.install"), ("Send message", "communication.send"),
                                  ("Delete object", "application.delete"), ("Submit form", "application.submit"),
                                  ("Change security setting", "application.security_settings")):
            self.kind.addItem(label, permission)
        layout.addWidget(self.kind)
        self.host = QWidget()
        self.form = QFormLayout(self.host)
        layout.addWidget(self.host)
        self.expected = QLineEdit()
        self.expected.setPlaceholderText("New visible control name proving completion")
        layout.addWidget(self.expected)
        self.status = QLabel("Select actual visible evidence. A separate exact-action confirmation follows. Paid installations require a separate purchase flow.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        button = QPushButton("Review action")
        button.clicked.connect(self.review)
        layout.addWidget(button)
        self.kind.currentIndexChanged.connect(self.fields)
        self.fields()

    def fields(self):
        while self.form.rowCount():
            self.form.removeRow(0)
        self.bindings = {}
        for field in REQUIRED_FIELDS[self.kind.currentData()]:
            if field == "source" and self.kind.currentData() == "software.install":
                continue
            combo = QComboBox()
            combo.addItem("Select evidence control", None)
            for control in self.controls:
                if not control.get("password"):
                    combo.addItem(control.get("name", "") or control.get("control_type", "Control"), control["runtime_id"])
            self.bindings[field] = combo
            self.form.addRow(field.replace("_", " ").title(), combo)

    def review(self):
        values = {key: widget.currentData() for key, widget in self.bindings.items()}
        if not all(values.values()) or not self.expected.text().strip():
            self.status.setText("Select each evidence field and the completion state")
            return
        self.bridge.call("desktop.consequence", lambda result, error: self.status.setText(error or "Result verified"),
            permission=self.kind.currentData(), target=self.target,
            bindings={key: {"runtime_id": value} for key, value in values.items()}, expected={"name": self.expected.text()})
