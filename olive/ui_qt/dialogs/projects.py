from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QTabWidget, QPlainTextEdit
from ..components.common import table, populate, selected, show_details
from shiboken6 import isValid
import json


class WorkspacesDialog(QDialog):
    def __init__(self, manager, parent=None, project_id=None):
        super().__init__(parent)
        self.manager = manager
        self.bridge = manager.bridge
        self.project_id = project_id
        self.setWindowTitle("OLIVE — Approved workspaces")
        self.resize(950, 550)
        layout = QVBoxLayout(self)
        self.table = table(["Workspace", "Folder", "Type", "Trust"])
        layout.addWidget(self.table)
        row = QHBoxLayout()
        for name, callback in [
            ("Open Studio", self.open_studio),
            ("Open IDE", self.open_ide),
            ("Changes", self.changes),
            ("Run tests", self.validate),
            ("Undo latest OLIVE task", self.rollback),
        ]:
            button = QPushButton(name)
            button.clicked.connect(callback)
            row.addWidget(button)
        layout.addLayout(row)
        self.bridge.call("data.workspaces", self.loaded)

    def loaded(self, values, error):
        if values is not None:
            populate(
                self.table,
                [v for v in values if not self.project_id or v["project_id"] == self.project_id],
                ["title", "root_path", "workspace_type", "trust_level"],
            )

    def open_studio(self):
        value = selected(self.table)
        if value:
            studio = self.manager.open("studio")
            studio.workspace_id = value["id"]
            studio.workspace.setCurrentIndex(studio.workspace.findData(value["id"]))
            studio.load_tree()
            self.accept()

    def open_ide(self):
        value = selected(self.table)
        if value:
            self.bridge.call(
                "agent.tool",
                name="ide.open_workspace",
                arguments={"workspace": value["root_path"], "path": value["root_path"]},
            )

    def changes(self):
        value = selected(self.table)
        if value:
            self.bridge.call(
                "studio.git",
                lambda v, e: show_details(self, "Workspace changes", v) if v else None,
                workspace_id=value["id"],
                action="diff",
            )

    def validate(self):
        value = selected(self.table)
        if value:
            self.bridge.call(
                "studio.validate",
                lambda v, e: show_details(self, "Validation", v) if v else None,
                workspace_id=value["id"],
            )

    def rollback(self):
        value = selected(self.table)
        if value:
            self.bridge.call(
                "studio.rollback_latest",
                lambda v, e: show_details(self, "Checkpoint restore", v) if v else None,
                workspace_id=value["id"],
            )


class ProjectDialog(QDialog):
    def __init__(self, manager, value, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.value = value
        self.setWindowTitle("OLIVE — " + value["Overview"]["title"])
        self.resize(1000, 680)
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        layout.addWidget(tabs)
        for title, items in value.items():
            fields = {
                "Chats": ["title", "model", "updated_at"],
                "Research": ["question", "created_at", "report"],
                "Web Knowledge": ["title", "url", "collection", "chunk_count", "status"],
                "Knowledge": ["name", "kind", "chunk_count", "indexed"],
                "Workspace/Files": ["title", "root_path", "trust_level"],
                "Tasks": ["user_request", "state", "updated_at"],
                "Memories": ["content", "category", "created_at"],
            }.get(title)
            if fields:
                widget = table([field.replace("_", " ").title() for field in fields])
                populate(widget, items, fields)
                widget.doubleClicked.connect(
                    lambda index, target=widget: show_details(self, "Details", selected(target))
                )
            else:
                widget = table(["Project", "Details"])
                populate(
                    widget,
                    [{"field": k.replace("_", " ").title(), "value": v} for k, v in items.items()],
                    ["field", "value"],
                )
            tabs.addTab(widget, title)
        history = QPlainTextEdit()
        history.setReadOnly(True)
        tabs.addTab(history, "Agent history")
        manager.bridge.call(
            "agent.actions",
            lambda v, e: (
                history.setPlainText(json.dumps(v, indent=2, ensure_ascii=False))
                if v is not None and isValid(history)
                else None
            ),
        )
        button = QPushButton("Workspace files / Git / validation")
        button.clicked.connect(self.workspaces)
        layout.addWidget(button)

    def workspaces(self):
        WorkspacesDialog(self.manager, self, self.value["Overview"]["id"]).exec()
