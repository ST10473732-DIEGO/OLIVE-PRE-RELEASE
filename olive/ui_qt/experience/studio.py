"""Retain the real docked IDE; add a focused entry state and shared density."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QStackedWidget, QFileDialog, QInputDialog, QComboBox
from ..studio.window import StudioWindow


class StudioExperience(StudioWindow):
    def __init__(self, manager):
        super().__init__(manager)
        self.setObjectName("studioMidnight")
        tabs = self.takeCentralWidget()
        self.content_host = QStackedWidget()
        self.content_host.addWidget(tabs)
        empty = QWidget(); layout = QVBoxLayout(empty); layout.setContentsMargins(40, 32, 40, 32)
        layout.addStretch()
        label = QLabel("Make something useful."); label.setObjectName("title"); label.setWordWrap(True); layout.addWidget(label)
        label = QLabel("Open a local workspace to edit, run and test alongside OLIVE.")
        label.setObjectName("quiet"); label.setWordWrap(True); layout.addWidget(label)
        button = QPushButton("Open workspace"); button.setObjectName("primary"); button.clicked.connect(lambda: self.open_workspace()); layout.addWidget(button)
        button = QPushButton("Create project"); button.clicked.connect(self.create_project); layout.addWidget(button)
        self.recent_workspaces = QComboBox(); self.recent_workspaces.setAccessibleName("Recent approved workspaces")
        self.recent_workspaces.activated.connect(self.open_recent); layout.addWidget(self.recent_workspaces)
        layout.addStretch()
        self.content_host.addWidget(empty); self.setCentralWidget(self.content_host)
        self.tabs.currentChanged.connect(self.update_empty)
        self.update_empty()

    def update_empty(self, *_):
        self.content_host.setCurrentIndex(0 if self.tabs.count() else 1)

    def workspaces_loaded(self, values, error):
        super().workspaces_loaded(values, error)
        self.recent_workspaces.clear(); self.recent_workspaces.addItem("Recent workspaces", None)
        for value in values or []:
            self.recent_workspaces.addItem(value["title"], value["id"])

    def open_recent(self):
        identity = self.recent_workspaces.currentData()
        if identity:
            self.workspace.setCurrentIndex(self.workspace.findData(identity)); self.select_workspace()

    def open_workspace(self, project_id=None):
        # A manual folder selection establishes the existing approved scope;
        # execution remains subject to Studio/Agent permission services.
        path = QFileDialog.getExistingDirectory(self, "Open and approve workspace folder")
        if not path: return
        def created(value, error):
            if value:
                self.workspace_id = value["id"]
                self.call("interaction.select_workspace", workspace_id=self.workspace_id)
                self.refresh()
        self.call("data.create_workspace", created, title="", path=path, project_id=project_id, trust_level="approved")

    def create_project(self):
        title, ok = QInputDialog.getText(self, "Create project", "Project name")
        if not ok or not title.strip(): return
        self.call("data.create_project", lambda value, error: self.open_workspace(value["id"]) if value else None, title=title.strip())
