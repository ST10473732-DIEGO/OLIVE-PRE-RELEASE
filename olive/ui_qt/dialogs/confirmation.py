import json
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPlainTextEdit, QDialogButtonBox, QCheckBox
from ..runtime import ConfirmationResponse


class ConfirmationDialog(QDialog):
    def __init__(self, request, parent=None):
        super().__init__(parent)
        self.request = request
        self.response = ConfirmationResponse(False)
        self.setWindowTitle("OLIVE — Review action")
        self.resize(620, 420)
        layout = QVBoxLayout(self)
        consequences = {"communication.send": ("Review message", "Send"), "application.upload": ("Review upload", "Upload"),
                        "software.install": ("Review installation", "Install"), "software.purchase": ("Review purchase", "Purchase"),
                        "application.delete": ("Review deletion", "Delete"), "application.submit": ("Review submission", "Submit")}
        consequence = consequences.get(request.tool_name)
        heading = QLabel(consequence[0] if consequence else "Permission to continue")
        heading.setObjectName("title")
        layout.addWidget(heading)
        layout.addWidget(QLabel(f"Tool: {request.tool_name}    Risk: {request.risk_level}"))
        text = QPlainTextEdit()
        text.setReadOnly(True)
        semantic = request.tool_name.startswith(("desktop.", "interactive.", "software.", "communication.", "application."))
        parameters = "\n\n".join(key.replace("_", " ").title() + ":\n" +
            ("\n".join(map(str, value)) if isinstance(value, list) else str(value))
            for key, value in request.arguments.items()) if semantic else json.dumps(request.arguments, indent=2, ensure_ascii=False)
        text.setPlainText(
            request.summary
            + "\n\nTarget / scope:\n"
            + "\n".join(request.targets)
            + "\n\nRequested parameters:\n"
            + parameters
        )
        layout.addWidget(text)
        self.remember = QCheckBox("Remember this application and action")
        self.remember.setVisible(request.allow_remember)
        layout.addWidget(self.remember)
        self.all_apps = QCheckBox("Remember this action for all applications")
        self.all_apps.setVisible(request.allow_remember)
        layout.addWidget(self.all_apps)
        buttons = QDialogButtonBox()
        buttons.addButton(consequence[1] if consequence else "Approve once", QDialogButtonBox.ButtonRole.AcceptRole).clicked.connect(
            self.approve
        )
        buttons.addButton("Edit" if request.tool_name == "communication.send" else "Cancel" if consequence else "Deny",
                          QDialogButtonBox.ButtonRole.RejectRole).clicked.connect(self.reject)
        buttons.addButton("Cancel task", QDialogButtonBox.ButtonRole.DestructiveRole).clicked.connect(
            self.cancel_task
        )
        layout.addWidget(buttons)

    def approve(self):
        self.response = ConfirmationResponse(
            True, remember=self.remember.isChecked(), remember_all=self.all_apps.isChecked()
        )
        self.accept()

    def cancel_task(self):
        self.response = ConfirmationResponse(False, cancel_task=True)
        self.reject()
