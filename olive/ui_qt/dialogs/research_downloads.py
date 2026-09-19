"""Explicit read, save and import actions for quarantined downloads."""

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLineEdit,
    QPlainTextEdit,
    QFileDialog,
)
from ..components.common import table, populate, selected


class ResearchDownloadsDialog(QDialog):
    def __init__(self, bridge, parent=None):
        super().__init__(parent)
        self.bridge = bridge
        self.setWindowTitle("OLIVE — Research downloads")
        self.resize(900, 650)
        layout = QVBoxLayout(self)
        self.url = QLineEdit()
        self.url.setPlaceholderText("Public document URL")
        layout.addWidget(self.url)
        row = QHBoxLayout()
        for title, callback in [
            ("Download to quarantine", self.download),
            ("Read as document", self.read),
            ("Save file", self.save),
            ("Import as Knowledge", self.learn),
            ("Remove", self.remove),
        ]:
            button = QPushButton(title)
            button.clicked.connect(callback)
            row.addWidget(button)
        layout.addLayout(row)
        self.table = table(["Filename", "Type", "Size", "State"])
        layout.addWidget(self.table)
        self.content = QPlainTextEdit()
        self.content.setReadOnly(True)
        layout.addWidget(self.content, 1)
        self.reload()

    def reload(self):
        self.bridge.call("research.downloads", self.loaded)

    def loaded(self, values, error):
        if values is not None:
            populate(self.table, values, ["filename", "content_type", "size", "state"])

    def finished_operation(self, value, error):
        self.content.setPlainText(error or str(value))
        self.reload()

    def download(self):
        self.bridge.call("research.download", self.finished_operation, url=self.url.text())

    def read(self):
        value = selected(self.table)
        if value:
            self.bridge.call("research.read_download", self.read_result, download_id=value["id"])

    def read_result(self, value, error):
        self.content.setPlainText(error or (value or {}).get("text", ""))

    def save(self):
        value = selected(self.table)
        if value:
            path, _ = QFileDialog.getSaveFileName(self, "Save quarantined file", value["filename"])
            if path:
                self.bridge.call(
                    "research.export_download",
                    self.finished_operation,
                    download_id=value["id"],
                    destination=path,
                )

    def learn(self):
        value = selected(self.table)
        if value:
            self.bridge.call("research.import_download", self.finished_operation, download_id=value["id"])

    def remove(self):
        value = selected(self.table)
        if value:
            self.bridge.call("research.remove_download", self.loaded, download_id=value["id"])
