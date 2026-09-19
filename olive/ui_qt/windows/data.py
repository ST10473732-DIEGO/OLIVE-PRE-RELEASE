from PySide6.QtCore import QTimer
from shiboken6 import isValid
from PySide6.QtWidgets import (
    QLineEdit,
    QComboBox,
    QInputDialog,
    QFileDialog,
    QMessageBox,
    QDialog,
    QVBoxLayout,
    QPushButton,
)
from .base import FeatureWindow
from ..dialogs.projects import ProjectDialog, WorkspacesDialog
from ..components.common import table, populate, selected, show_details


class DataWindow(FeatureWindow):
    def __init__(self, manager, feature_id):
        super().__init__(manager, feature_id)
        self.values = []
        layout = self.page(
            manager.registry.get(feature_id).title, manager.registry.get(feature_id).description
        )
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search")
        self.search.textChanged.connect(self.filter)
        layout.addWidget(self.search)
        actions = [("Refresh", self.refresh)]
        if feature_id == "projects":
            self.fields = ["title", "description"]
            columns = ["Project", "Description"]
            actions += [
                ("New project", self.new_project),
                ("Open project", self.open_project),
                ("Add workspace", self.add_workspace),
                ("Workspaces", self.workspaces),
            ]
        elif feature_id == "memory":
            self.fields = ["content", "category", "source_title", "created_at", "confidence"]
            columns = ["Memory", "Category", "Source chat", "Created", "Confidence"]
            actions += [
                ("Add", self.add_memory),
                ("Edit", self.edit_memory),
                ("Delete", self.delete_memory),
                ("Suggestions", self.suggestions),
                ("Export", self.export_memory),
            ]
            self.category = QComboBox()
            self.category.addItem("All")
            self.category.currentTextChanged.connect(self.filter)
            layout.addWidget(self.category)
        else:
            self.fields = ["name", "chat_title", "kind", "chunk_count", "embedding_indexed", "health"]
            columns = ["Document", "Conversation", "Type", "Chunks", "Semantic", "Health"]
            actions += [
                ("Add", self.add_document),
                ("Web sources / Learn website", self.web_knowledge),
                ("Re-index", self.reindex),
                ("Relink", self.relink),
                ("Remove", self.remove_document),
                ("Indexing jobs", self.jobs),
                ("Retrieval inspector", self.retrieve),
                ("Upgrade lexical indexes", lambda: self.call("knowledge.upgrade")),
            ]
        self.buttons(layout, actions)
        self.table = table(columns)
        layout.addWidget(self.table, 1)
        self.table.doubleClicked.connect(self.details)

    def web_knowledge(self):
        from ..dialogs.web_knowledge import WebKnowledgeDialog
        WebKnowledgeDialog(self.manager, self).exec()

    def refresh(self):
        operation = {"projects": "data.projects", "memory": "data.memories", "knowledge": "knowledge.list"}[
            self.feature_id
        ]
        self.call(operation, self.loaded)

    def loaded(self, values, error=""):
        if values is None:
            return
        self.values = values
        if self.feature_id == "memory":
            current = self.category.currentText()
            self.category.blockSignals(True)
            self.category.clear()
            self.category.addItems(["All"] + sorted({v["category"] for v in values}))
            self.category.setCurrentText(current)
            self.category.blockSignals(False)
        self.filter()

    def filter(self, *args):
        needle = self.search.text().casefold()
        if self.feature_id == "memory":
            category = self.category.currentText()

            def filtered(values, error):
                if values is not None and needle == self.search.text().casefold() and category == self.category.currentText():
                    populate(self.table, values, self.fields)

            self.call("data.memories", filtered, query=needle, category=category)
            return
        rows = [value for value in self.values if needle in str(value).casefold()]
        populate(self.table, rows, self.fields)

    def details(self):
        value = selected(self.table)
        if value:
            if self.feature_id == "projects":
                self.open_project()
            else:
                show_details(self, "Source details", value)

    def on_event(self, topic, value):
        super().on_event(topic, value)
        if topic == {"projects": "projects", "memory": "memories", "knowledge": "knowledge"}.get(
            self.feature_id
        ):
            self.loaded(value)
        if topic == "memory_suggestion" and self.feature_id == "memory":
            self.statusBar().showMessage("A memory suggestion is ready for review", 15000)

    def new_project(self):
        title, ok = QInputDialog.getText(self, "New project", "Title")
        if ok and title:
            self.call("data.create_project", lambda v, e: self.refresh(), title=title)

    def open_project(self):
        value = selected(self.table)
        if value:
            self.call(
                "data.project_detail",
                lambda v, e: ProjectDialog(self.manager, v, self).exec() if v else None,
                project_id=value["id"],
            )

    def add_workspace(self):
        path = QFileDialog.getExistingDirectory(self, "Approve workspace folder")
        if not path:
            return
        trust, ok = QInputDialog.getItem(
            self,
            "Workspace execution trust",
            "Trust level",
            ["approved", "trusted", "untrusted"],
            editable=False,
        )
        if ok:
            value = selected(self.table)
            self.call(
                "data.create_workspace",
                lambda v, e: self.refresh(),
                title="",
                path=path,
                project_id=value["id"] if value else None,
                trust_level=trust,
            )

    def workspaces(self):
        WorkspacesDialog(self.manager, self).exec()

    def add_memory(self):
        text, ok = QInputDialog.getMultiLineText(self, "Add memory", "Durable fact or preference")
        if ok:
            self.call("data.memory_save", self.loaded, content=text)

    def edit_memory(self):
        value = selected(self.table)
        if value:
            text, ok = QInputDialog.getMultiLineText(self, "Edit memory", "Memory", value["content"])
            if ok:
                self.call(
                    "data.memory_save",
                    self.loaded,
                    content=text,
                    memory_id=value["id"],
                    category=value["category"],
                )

    def delete_memory(self):
        value = selected(self.table)
        if (
            value
            and QMessageBox.question(self, "Delete memory", "Remove this memory?")
            == QMessageBox.StandardButton.Yes
        ):
            self.call("data.memory_delete", self.loaded, memory_id=value["id"])

    def suggestions(self):
        def review(values, error):
            for value in values or []:
                text, ok = QInputDialog.getMultiLineText(
                    self,
                    "Review memory suggestion",
                    f"{value['category']} · confidence {value['confidence']:.0%}",
                    value["content"],
                )
                self.call(
                    "data.review_suggestion", self.loaded, suggestion_id=value["id"], approve=ok, content=text
                )
            if not values:
                self.statusBar().showMessage("No pending memory suggestions", 5000)

        self.call("data.suggestions", review)

    def export_memory(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export memories", "memories.json", "JSON (*.json)")
        if path:
            self.call("data.export", path=path, kind="memory")

    def add_document(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Add knowledge to current conversation")
        if paths:
            self.call(
                "chat.get",
                lambda v, e: (
                    self.call("knowledge.attach", self.loaded, chat_id=v["id"], paths=paths, permanent=True)
                    if v
                    else None
                ),
            )

    def reindex(self):
        value = selected(self.table)
        if value:
            self.call("knowledge.reindex", self.loaded, chat_id=value["chat_id"], document_id=value["id"])

    def relink(self):
        value = selected(self.table)
        if value:
            path, _ = QFileDialog.getOpenFileName(self, "Relink document source")
            if path:
                self.call(
                    "knowledge.relink",
                    lambda v, e: self.refresh(),
                    chat_id=value["chat_id"],
                    document_id=value["id"],
                    path=path,
                )

    def remove_document(self):
        value = selected(self.table)
        if (
            value
            and QMessageBox.question(
                self, "Remove knowledge", "Remove this document index? Source file will remain."
            )
            == QMessageBox.StandardButton.Yes
        ):
            self.call("knowledge.remove", self.loaded, chat_id=value["chat_id"], document_id=value["id"])

    def retrieve(self):
        query, ok = QInputDialog.getText(self, "Retrieval inspector", "Query current conversation knowledge")
        if ok:
            self.call(
                "chat.get",
                lambda v, e: (
                    self.call(
                        "knowledge.retrieve",
                        lambda r, error: (
                            show_details(self, "Retrieval scores and sources", r) if r is not None else None
                        ),
                        chat_id=v["id"],
                        query=query,
                    )
                    if v
                    else None
                ),
            )

    def jobs(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("OLIVE — Indexing jobs")
        dialog.resize(850, 480)
        layout = QVBoxLayout(dialog)
        widget = table(["File", "State", "Progress", "Error"])
        layout.addWidget(widget)

        def refresh():
            self.call(
                "knowledge.jobs",
                lambda v, e: (
                    populate(widget, v or [], ["filename", "state", "progress", "error"])
                    if isValid(widget) and dialog.isVisible()
                    else None
                ),
            )

        def action(name):
            value = selected(widget)
            if value:
                self.call("knowledge.job_action", lambda v, e: refresh(), job_id=value["id"], action=name)

        for name in ("pause", "resume", "cancel", "retry"):
            button = QPushButton(name.title())
            button.clicked.connect(lambda checked=False, n=name: action(n))
            layout.addWidget(button)
        timer = QTimer(dialog)
        timer.timeout.connect(refresh)
        timer.start(1000)
        QTimer.singleShot(0, refresh)
        dialog.exec()
        timer.stop()
