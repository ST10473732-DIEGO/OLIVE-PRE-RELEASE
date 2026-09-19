from PySide6.QtWidgets import QDialog, QVBoxLayout, QPlainTextEdit, QPushButton, QLabel


class ClipboardDialog(QDialog):
    def __init__(self, bridge, parent=None):
        super().__init__(parent)
        self.setWindowTitle("OLIVE - Clipboard")
        self.resize(600, 360)
        layout = QVBoxLayout(self)
        editor = QPlainTextEdit()
        layout.addWidget(editor)
        status = QLabel("Clipboard contents stay in this dialog and are not saved to Knowledge or Memory.")
        status.setWordWrap(True)
        layout.addWidget(status)
        def read(result, error=""):
            if error:
                status.setText(error)
            else:
                editor.setPlainText(result["text"])
        button = QPushButton("Review clipboard read")
        button.clicked.connect(lambda: bridge.call("desktop.clipboard_action", read, action="read"))
        layout.addWidget(button)
        button = QPushButton("Review replacing clipboard text")
        button.clicked.connect(lambda: bridge.call("desktop.clipboard_action", lambda result, error: status.setText(error or "Clipboard write verified"), action="write", text=editor.toPlainText()))
        layout.addWidget(button)
        self.finished.connect(lambda result: editor.clear())
