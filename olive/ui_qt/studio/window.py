from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QDockWidget,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTreeWidget,
    QTreeWidgetItem,
    QTabWidget,
    QPlainTextEdit,
    QPushButton,
    QComboBox,
    QLineEdit,
    QLabel,
    QToolBar,
)
from ..windows.base import FeatureWindow
from ..components.common import table
from .native_editor import NativeEditor
from .actions import StudioActions


class StudioWindow(StudioActions, FeatureWindow):
    def __init__(self, manager):
        super().__init__(manager, "studio")
        self.resize(1400, 900)
        self.setMinimumSize(900, 650)
        self.workspace_id = manager.state.get("studio").get("workspace_id")
        self.workspace_values = {}
        self.documents = {}
        self.session_id = None
        self.preview = None
        self.recent = []
        self.saving = set()
        self.setDockNestingEnabled(True)
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self.editor_changed)
        self.tabs.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tabs.customContextMenuRequested.connect(self.tab_menu)
        self.setCentralWidget(self.tabs)
        toolbar = QToolBar("Studio actions", self)
        toolbar.setObjectName("studio-toolbar")
        self.addToolBar(toolbar)
        self.workspace = QComboBox()
        self.workspace.setMinimumWidth(240)
        self.workspace.setAccessibleName("Studio workspace")
        self.workspace.activated.connect(self.select_workspace)
        toolbar.addWidget(self.workspace)
        for label, callback, shortcut in [
            ("Save", self.save, "Ctrl+S"),
            ("Save all", self.save_all, "Ctrl+Shift+S"),
            ("Quick open", self.quick_open, "Ctrl+P"),
            ("Search", self.search_workspace, "Ctrl+Shift+F"),
            ("Run", self.run, ""),
            ("Stop", self.stop, ""),
            ("Restart", self.restart, ""),
            ("Preview", self.open_preview, ""),
            ("Research", self.research, ""),
        ]:
            action = toolbar.addAction(label)
            action.triggered.connect(callback)
            if shortcut:
                action.setShortcut(QKeySequence(shortcut))
        self.explorer = QTreeWidget()
        self.explorer.setHeaderLabels(["Workspace files"])
        self.explorer.itemDoubleClicked.connect(self.tree_open)
        explorer_host = QWidget()
        box = QVBoxLayout(explorer_host)
        refresh = QPushButton("Refresh explorer")
        refresh.clicked.connect(self.load_tree)
        box.addWidget(refresh)
        box.addWidget(self.explorer)
        self.explorer_dock = self.dock("Explorer", explorer_host, Qt.DockWidgetArea.LeftDockWidgetArea)
        assistant = QWidget()
        box = QVBoxLayout(assistant)
        box.addWidget(QLabel("OLIVE ASSISTANT"))
        self.request = QPlainTextEdit()
        self.request.setPlaceholderText("Ask about this workspace or the active selection…")
        box.addWidget(self.request)
        button = QPushButton("Start coding task")
        button.setObjectName("primary")
        button.clicked.connect(self.ask)
        box.addWidget(button)
        self.ai_status = QLabel("Ready")
        self.ai_status.setWordWrap(True)
        box.addWidget(self.ai_status)
        self.assistant_dock = self.dock("Assistant", assistant, Qt.DockWidgetArea.RightDockWidgetArea)
        self.problems = table(["Severity", "File", "Line", "Code", "Message", "Source"])
        self.problems.doubleClicked.connect(self.open_problem)
        self.problems_dock = self.dock("Problems", self.problems, Qt.DockWidgetArea.BottomDockWidgetArea)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.document().setMaximumBlockCount(6000)
        self.output_dock = self.dock("Output", self.output, Qt.DockWidgetArea.BottomDockWidgetArea)
        terminal = QWidget()
        box = QVBoxLayout(terminal)
        self.terminal_output = QPlainTextEdit()
        self.terminal_output.setReadOnly(True)
        self.terminal_output.document().setMaximumBlockCount(6000)
        box.addWidget(self.terminal_output)
        self.command = QLineEdit()
        self.command.setPlaceholderText("PowerShell command — approval rules apply")
        self.command.returnPressed.connect(self.run_terminal)
        box.addWidget(self.command)
        button = QPushButton("Execute command")
        button.clicked.connect(self.run_terminal)
        box.addWidget(button)
        self.terminal_dock = self.dock("Terminal", terminal, Qt.DockWidgetArea.BottomDockWidgetArea)
        self.tests = table(["Test", "Status", "Duration", "Message", "File"])
        tests_host = QWidget()
        box = QVBoxLayout(tests_host)
        box.addWidget(self.tests)
        button = QPushButton("Run all detected tests")
        button.clicked.connect(self.run_tests)
        box.addWidget(button)
        for label in ("Run failed", "Run selected"):
            button = QPushButton(label)
            button.setEnabled(False)
            button.setToolTip(
                "The current backend runner supports whole-suite validation. Use Run all detected tests."
            )
            box.addWidget(button)
        self.tests_dock = self.dock("Tests", tests_host, Qt.DockWidgetArea.BottomDockWidgetArea)
        self.git_output = QPlainTextEdit()
        self.git_output.setReadOnly(True)
        self.git_output.document().setMaximumBlockCount(6000)
        git_host = QWidget()
        box = QVBoxLayout(git_host)
        self.git_branch = QLabel("Branch: not loaded")
        box.addWidget(self.git_branch)
        self.git_files = table(["File", "Staged", "Worktree"])
        self.git_files.setMaximumHeight(150)
        box.addWidget(self.git_files)
        box.addWidget(self.git_output)
        row = QHBoxLayout()
        for label, callback in [
            ("Refresh", self.git_status),
            ("Diff", lambda: self.git_action("diff")),
            ("Staged diff", lambda: self.git_action("diff", staged=True)),
            ("Log", lambda: self.git_action("log")),
            ("Stage file", self.git_stage),
            ("Commit", self.git_commit),
            ("Branches", lambda: self.git_action("branch_list")),
        ]:
            button = QPushButton(label)
            button.clicked.connect(callback)
            row.addWidget(button)
        box.addLayout(row)
        self.git_dock = self.dock("Git", git_host, Qt.DockWidgetArea.BottomDockWidgetArea)
        for dock in (self.terminal_dock, self.tests_dock, self.git_dock, self.problems_dock):
            self.tabifyDockWidget(self.output_dock, dock)
        self.output_dock.raise_()
        self.resizeDocks([self.explorer_dock, self.assistant_dock], [230, 280], Qt.Orientation.Horizontal)
        self.resizeDocks([self.output_dock], [230], Qt.Orientation.Vertical)
        self.default_layout = self.saveState()
        view = self.menuBar().addMenu("View")
        for dock in self.findChildren(QDockWidget):
            view.addAction(dock.toggleViewAction())
        view.addAction("Reset layout", self.reset_layout)
        edit = self.menuBar().addMenu("Editor")
        for name, callback in [
            ("Find / replace", self.find_replace),
            ("Go to line", self.go_to_line),
            ("Reopen recent", self.reopen_recent),
        ]:
            edit.addAction(name, callback)
        action = QAction(self)
        action.setShortcut(QKeySequence("Ctrl+`"))
        action.triggered.connect(lambda: self.terminal_dock.setVisible(not self.terminal_dock.isVisible()))
        self.addAction(action)
        self.restore_documents = manager.state.get("studio").get("documents", [])
        if not isinstance(self.restore_documents, list):
            self.restore_documents = []

    def dock(self, name, widget, area):
        dock = QDockWidget(name, self)
        dock.setObjectName("studio-" + name.lower())
        dock.setWidget(widget)
        self.addDockWidget(area, dock)
        return dock

    def refresh(self):
        self.call("data.workspaces", self.workspaces_loaded)

    def workspaces_loaded(self, values, error):
        if values is None:
            return
        self.workspace_values = {value["id"]: value for value in values}
        self.workspace.blockSignals(True)
        self.workspace.clear()
        self.workspace.addItem("Select approved workspace", None)
        for value in values:
            self.workspace.addItem(value["title"], value["id"])
        self.workspace.setCurrentIndex(max(0, self.workspace.findData(self.workspace_id)))
        self.workspace.blockSignals(False)
        if self.restore_documents:
            documents, self.restore_documents = self.restore_documents, []
            for document in documents[:30]:
                if (
                    isinstance(document, dict)
                    and document.get("workspace_id") in self.workspace_values
                    and isinstance(document.get("path"), str)
                ):
                    self.open_file(document["path"], workspace_id=document["workspace_id"])
        if self.workspace_id in self.workspace_values and self.explorer.topLevelItemCount() == 0:
            self.load_tree()

    def layout_state(self):
        return {
            "workspace_id": self.workspace_id,
            "documents": [
                {"workspace_id": d["workspace_id"], "path": d["path"]}
                for d in list(self.documents.values())[:30]
            ],
        }

    def select_workspace(self):
        self.workspace_id = self.workspace.currentData()
        self.call("interaction.select_workspace", workspace_id=self.workspace_id)
        self.load_tree()
        if self.workspace_id:
            self.git_status()

    def load_tree(self):
        if self.workspace_id:
            self.call("studio.access", self.tree_loaded, workspace_id=self.workspace_id, action="tree")

    def tree_loaded(self, value, error):
        if not value:
            return
        self.explorer.clear()
        nodes = {}
        for item in value["entries"]:
            parts = item["path"].split("/")
            parent = self.explorer.invisibleRootItem()
            for index, part in enumerate(parts):
                path = "/".join(parts[: index + 1])
                if path not in nodes:
                    node = QTreeWidgetItem([part])
                    node.setData(
                        0,
                        Qt.ItemDataRole.UserRole,
                        {"path": path, "directory": index < len(parts) - 1 or item["directory"]},
                    )
                    parent.addChild(node)
                    nodes[path] = node
                parent = nodes[path]

    def tree_open(self, item, column=0):
        value = item.data(0, Qt.ItemDataRole.UserRole)
        if value and not value["directory"]:
            self.open_file(value["path"])

    def open_file(self, path, line=1, workspace_id=None):
        workspace_id = workspace_id or self.workspace_id
        if not workspace_id:
            return
        key = (workspace_id, path)
        if key in self.documents:
            editor = self.documents[key]["editor"]
            self.tabs.setCurrentWidget(editor)
            editor.go_to_line(line)
            return
        self.call(
            "studio.access",
            lambda v, e: self.file_loaded(workspace_id, path, line, v, e),
            workspace_id=workspace_id,
            action="open",
            path=path,
        )

    def file_loaded(self, workspace_id, path, line, value, error):
        if not value:
            return
        key = (workspace_id, path)
        if key in self.documents:
            self.tabs.setCurrentWidget(self.documents[key]["editor"])
            return
        editor = NativeEditor()
        editor.set_text(value["text"])
        from PySide6.QtGui import QFont

        settings = self.manager.settings
        editor.setFont(QFont(settings.get("editor_font", "Consolas"), int(settings.get("editor_size", 13))))
        editor.tab_spaces = int(settings.get("editor_tab_width", 4))
        editor.setTabStopDistance(editor.fontMetrics().horizontalAdvance(" ") * editor.tab_spaces)
        suffix = Path(path).suffix.lower()
        editor.set_language("text" if suffix in {".txt", ".log"} else suffix)
        self.documents[key] = {
            "editor": editor,
            "hash": value["loaded_hash"],
            "saved": value["saved_text"],
            "path": path,
            "workspace_id": workspace_id,
        }
        index = self.tabs.addTab(editor, Path(path).name)
        self.tabs.setTabToolTip(index, path)
        self.tabs.setCurrentIndex(index)
        editor.document().modificationChanged.connect(lambda dirty, ed=editor: self.dirty_changed(ed, dirty))
        editor.ai_requested.connect(self.inline_action)
        editor.cursorPositionChanged.connect(self.editor_changed)
        editor.go_to_line(line)
        self.recent = [key] + [k for k in self.recent if k != key]
        self.recent = self.recent[:20]

    def active_document(self):
        return next((d for d in self.documents.values() if d["editor"] is self.tabs.currentWidget()), None)

    def dirty_changed(self, editor, dirty):
        index = self.tabs.indexOf(editor)
        if index >= 0:
            document = next(d for d in self.documents.values() if d["editor"] is editor)
            self.tabs.setTabText(index, Path(document["path"]).name + (" *" if dirty else ""))

    def editor_changed(self, *args):
        doc = self.active_document()
        if doc:
            line, column = doc["editor"].cursor_position()
            self.statusBar().showMessage(f"{doc['path']}   ·   Ln {line}, Col {column}")
            if self.workspace_id != doc["workspace_id"]:
                self.workspace_id = doc["workspace_id"]
                self.workspace.setCurrentIndex(self.workspace.findData(self.workspace_id))

    def reset_layout(self):
        self.restoreState(self.default_layout)
        for dock in self.findChildren(QDockWidget):
            dock.show()
        self.output_dock.raise_()
