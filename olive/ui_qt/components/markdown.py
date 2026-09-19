"""Markdown display without active content or automatic remote resource loading."""

import re
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QTextBrowser,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QApplication,
)


class SafeMarkdown(QTextBrowser):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setOpenLinks(False)
        self.setOpenExternalLinks(False)
        self.anchorClicked.connect(self.open_link)

    def loadResource(self, kind, url):
        # Message text never receives filesystem, network, or execution capabilities.
        return None

    def open_link(self, url):
        if url.scheme() in {"http", "https", "mailto"}:
            QDesktopServices.openUrl(url)


class MessageWidget(QWidget):
    def __init__(self, message, details, branch=None):
        super().__init__()
        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(QLabel(message["role"].title()))
        row.addStretch()
        copy = QPushButton("Copy")
        copy.clicked.connect(lambda: QApplication.clipboard().setText(message["content"]))
        row.addWidget(copy)
        if message.get("sources") or message.get("memory_ids") or message.get("grounding"):
            button = QPushButton("Sources & provenance")
            button.clicked.connect(lambda: details(message))
            row.addWidget(button)
        if branch:
            button = QPushButton("Next alternative")
            button.clicked.connect(branch)
            row.addWidget(button)
        layout.addLayout(row)
        self.body = SafeMarkdown()
        self.body.setMarkdown(message["content"])
        self.body.setMinimumHeight(110)
        self.body.document().setTextWidth(750)
        height = min(600, max(110, int(self.body.document().size().height()) + 30))
        self.body.setFixedHeight(height)
        layout.addWidget(self.body)
        for index, block in enumerate(re.findall(r"```[^\n]*\n(.*?)```", message["content"], re.S), 1):
            button = QPushButton(f"Copy code {index}")
            button.clicked.connect(lambda checked=False, text=block: QApplication.clipboard().setText(text))
            layout.addWidget(button)
