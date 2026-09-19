"""Review a bounded website scope before asking the authoritative tools to save it."""

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QPlainTextEdit,
    QComboBox,
    QSpinBox,
    QLineEdit,
    QPushButton,
    QLabel,
)
from ..components.common import table, populate, selected


class WebKnowledgeDialog(QDialog):
    def __init__(self, manager, parent=None):
        super().__init__(parent)
        self.bridge = manager.bridge
        self.scope_urls = []
        self.setWindowTitle("OLIVE — Web Knowledge")
        self.resize(950, 750)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Learn selected pages. Permanent saving requires approval."))
        self.urls = QPlainTextEdit()
        self.urls.setPlaceholderText("Public HTTP(S) URLs, one per line")
        self.urls.setMaximumHeight(100)
        layout.addWidget(self.urls)
        row = QHBoxLayout()
        self.mode = QComboBox()
        self.mode.addItems(["single", "selected", "subsection", "sitemap"])
        self.limit = QSpinBox()
        self.limit.setRange(1, 30)
        self.limit.setValue(5)
        self.collection = QLineEdit("Web Knowledge")
        self.project = QComboBox()
        self.project.addItem("Global Knowledge", None)
        for widget in (self.mode, self.limit, self.collection, self.project):
            row.addWidget(widget)
        layout.addLayout(row)
        self.scope_view = QPlainTextEdit()
        self.scope_view.setReadOnly(True)
        self.scope_view.setMaximumHeight(120)
        layout.addWidget(self.scope_view)
        self.status = QLabel("Review the exact scope before saving.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        row = QHBoxLayout()
        for title, callback in [
            ("Review scope", self.review),
            ("Save reviewed pages", self.learn),
            ("Refresh source", self.refresh_source),
            ("Remove source", self.remove_source),
            ("Reload", self.reload),
        ]:
            button = QPushButton(title)
            button.clicked.connect(callback)
            row.addWidget(button)
        layout.addLayout(row)
        self.table = table(["Title", "Collection", "URL", "Retrieved", "State"])
        self.table.itemSelectionChanged.connect(self.inspect)
        layout.addWidget(self.table, 1)
        self.content = QPlainTextEdit()
        self.content.setReadOnly(True)
        layout.addWidget(self.content, 1)
        self.urls.textChanged.connect(self.invalidate)
        self.mode.currentTextChanged.connect(self.invalidate)
        self.limit.valueChanged.connect(self.invalidate)
        self.bridge.call("data.projects", self.projects_loaded)
        self.reload()

    def projects_loaded(self, values, error):
        for value in values or []:
            self.project.addItem(value["title"], value["id"])

    def invalidate(self, *args):
        self.scope_urls = []
        self.scope_view.clear()

    def review(self):
        urls = [line.strip() for line in self.urls.toPlainText().splitlines() if line.strip()]
        self.bridge.call(
            "research.scope", self.reviewed, urls=urls, mode=self.mode.currentText(), limit=self.limit.value()
        )

    def reviewed(self, value, error):
        if value:
            self.scope_urls = value["urls"]
            self.scope_view.setPlainText("\n".join(self.scope_urls))
            self.status.setText(
                f"Reviewed scope: {len(self.scope_urls)} pages. Saving will request approval."
            )
        elif error:
            self.status.setText(error)

    def learn(self):
        if self.scope_urls:
            self.bridge.call(
                "research.learn_urls",
                self.finished_operation,
                urls=self.scope_urls,
                project_id=self.project.currentData(),
                collection=self.collection.text(),
            )
        else:
            self.status.setText("Review a scope first.")

    def finished_operation(self, value, error):
        self.status.setText(error or str(value))
        self.reload()

    def reload(self):
        self.bridge.call("research.web_sources", self.loaded)

    def loaded(self, values, error):
        if values is not None:
            populate(self.table, values, ["title", "collection", "url", "retrieved_at", "status"])

    def inspect(self):
        source = selected(self.table)
        if source:
            self.bridge.call("research.web_source", self.show_content, source_id=source["id"])

    def show_content(self, value, error):
        if value:
            self.content.setPlainText(value["text"])

    def refresh_source(self):
        source = selected(self.table)
        if source:
            self.bridge.call("research.refresh_web", self.finished_operation, source_id=source["id"])

    def remove_source(self):
        source = selected(self.table)
        if source:
            self.bridge.call("research.remove_web", self.finished_operation, source_id=source["id"])
