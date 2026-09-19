from PySide6.QtWidgets import (
    QTabWidget,
    QWidget,
    QFormLayout,
    QLineEdit,
    QPlainTextEdit,
    QCheckBox,
    QComboBox,
    QSpinBox,
    QDoubleSpinBox,
    QInputDialog,
    QPushButton,
    QFileDialog,
    QMessageBox,
    QApplication,
    QScrollArea,
    QLabel,
    QTreeWidget,
    QTreeWidgetItem,
)
from .base import FeatureWindow
from ..themes import THEME_NAMES
from ..components.common import show_details
from ..dialogs.permissions import PermissionDialog
from ...config import PROMPT_PRESETS


class SettingsWindow(FeatureWindow):
    def __init__(self, manager):
        super().__init__(manager, "settings")
        layout = self.page("Settings", "All changes apply to the shared OLIVE runtime.")
        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.TabPosition.West)
        layout.addWidget(self.tabs, 1)
        self.forms = {}
        self.controls = {}
        self.snapshot = None
        for title in (
            "General",
            "Appearance",
            "Models",
            "Chat",
            "Agent",
            "Permissions",
            "Memory",
            "Knowledge/RAG",
            "Research",
            "Desktop Control",
            "Indexing",
            "OCR",
            "Studio",
            "Execution",
            "Backup & Data",
            "Advanced",
        ):
            widget = QWidget()
            form = QFormLayout(widget)
            form.setContentsMargins(20, 20, 20, 20)
            area = QScrollArea()
            area.setWidgetResizable(True)
            area.setWidget(widget)
            self.tabs.addTab(area, title)
            self.forms[title] = form
        self.forms["General"].addRow(QLabel("OLIVE is local-first. Ollama is the default runtime."))
        desktop = QPushButton("Desktop Control policies and safety")
        def desktop_settings():
            from ..dialogs.desktop_settings import DesktopSettingsDialog
            DesktopSettingsDialog(self.bridge, self).exec()
        desktop.clicked.connect(desktop_settings)
        self.forms["Desktop Control"].addRow(desktop)
        self.add("Appearance", "theme", "Theme", THEME_NAMES)
        self.add("Models", "embedding_model", "Embedding model")
        self.add("Models", "alias", "Current model nickname", group="alias")
        stack = QPushButton("Model roles, residency and local benchmarks")
        stack.clicked.connect(self.model_stack)
        self.forms["Models"].addRow(stack)
        button = QPushButton("Refresh installed models")
        button.clicked.connect(lambda: self.call("data.refresh_models"))
        self.forms["Models"].addRow(button)
        install = QPushButton("Install an Ollama model?")
        install.clicked.connect(self.install_model)
        self.forms["Models"].addRow(install)
        for key, label, limits in [
            ("temperature", "Temperature", (0.0, 2.0)),
            ("top_p", "Top P", (0.01, 1.0)),
            ("repeat_penalty", "Repeat penalty", (0.0, 2.0)),
            ("max_tokens", "Maximum tokens", (64, 131072)),
            ("history_messages", "History messages", (0, 1000)),
            ("rag_top_k", "RAG chunks", (1, 50)),
        ]:
            self.add("Chat", key, label, limits, group="params")
        self.add("Chat", "system_prompt", "System prompt", group="prompt")
        presets = QComboBox()
        presets.addItems(PROMPT_PRESETS)
        presets.activated.connect(
            lambda: self.controls["system_prompt"][0].setPlainText(PROMPT_PRESETS[presets.currentText()])
        )
        self.forms["Chat"].addRow("Prompt preset", presets)
        for key, label in [
            ("automatic_memory_suggestions", "Automatic suggestions"),
            ("memory_model_extraction", "Local-model suggestions"),
            ("auto_memory_approval", "Automatically approve suggestions"),
        ]:
            self.add("Memory", key, label, True)
        for key, label in [
            ("rag_semantic_weight", "Semantic weight"),
            ("rag_lexical_weight", "Lexical weight"),
            ("rag_minimum_score", "Minimum score"),
        ]:
            self.add("Knowledge/RAG", key, label, (0.0, 1.0))
        reset = QPushButton("Reset RAG defaults")
        reset.clicked.connect(self.reset_rag)
        self.forms["Knowledge/RAG"].addRow(reset)
        self.add("Indexing", "max_indexing_workers", "Workers", (1, 3))
        for key, label, limits in [
            ("max_searches", "Maximum searches", (1, 10)),
            ("max_pages", "Maximum pages", (1, 30)),
            ("max_link_depth", "Maximum link depth", (0, 3)),
            ("timeout", "Session timeout (seconds)", (15, 900)),
            ("page_concurrency", "Concurrent page reads", (1, 4)),
            ("page_timeout", "Page timeout (seconds)", (5, 60)),
            ("cache_lifetime", "Cache lifetime (seconds)", (0, 604800)),
        ]:
            self.add("Research", key, label, limits, group="research")
        self.add("Research", "browser_provider", "Browser provider", ["auto", "http", "playwright"], group="research")
        self.add("Research", "search_provider", "Search provider", ["ddgs", "searxng"], group="research")
        self.add("Research", "search_endpoint", "SearXNG endpoint", group="research")
        self.add("Research", "depth", "Default depth", ["Quick", "Standard", "Deep"], group="research")
        self.add("Research", "default_save_to_knowledge", "Prefer saving after review (approval still required)", True, group="research")
        self.add("OCR", "ocr_executable", "Tesseract executable")
        browse = QPushButton("Choose Tesseract")
        browse.clicked.connect(self.choose_ocr)
        self.forms["OCR"].addRow(browse)
        permissions = QPushButton("Edit global, folder and remembered app rules")
        permissions.clicked.connect(lambda: PermissionDialog(self.bridge, self).exec())
        self.forms["Permissions"].addRow(permissions)
        self.forms["Agent"].addRow(
            QLabel("Pause takes effect between tools. Permissions remain authoritative.")
        )
        self.add("Studio", "editor_font", "Editor font")
        self.add("Studio", "editor_size", "Editor font size", (9, 28))
        self.add("Studio", "editor_tab_width", "Tab width", (2, 8))
        self.forms["Execution"].addRow(
            QLabel("Native execution for approved workspaces. Untrusted execution requires Docker.")
        )
        button = QPushButton("Inspect execution availability")
        button.clicked.connect(lambda: self.manager.open("diagnostics"))
        self.forms["Execution"].addRow(button)
        for label, callback in [
            ("Create backup", self.backup),
            ("Restore backup", self.restore),
            ("Export memories", self.export_memories),
            ("Data maintenance", self.maintenance),
        ]:
            button = QPushButton(label)
            button.clicked.connect(callback)
            self.forms["Backup & Data"].addRow(button)
        self.forms["Advanced"].addRow(
            QLabel("UI layout is stored separately. Reset Studio layout from its View menu.")
        )
        self.buttons(layout, [("Reload", self.refresh), ("Save settings", self.save)])

    def add(self, category, key, label, kind=None, group="settings"):
        if kind is True:
            control = QCheckBox()
        elif isinstance(kind, list):
            control = QComboBox()
            control.addItems(kind)
        elif isinstance(kind, tuple):
            control = QDoubleSpinBox() if isinstance(kind[0], float) else QSpinBox()
            control.setRange(*kind)
            if isinstance(control, QDoubleSpinBox):
                control.setSingleStep(0.05)
                control.setDecimals(3)
        elif group == "prompt":
            control = QPlainTextEdit()
            control.setMinimumHeight(150)
        else:
            control = QLineEdit()
        control.setAccessibleName(label)
        self.controls[key] = (control, group)
        self.forms[category].addRow(label, control)

    def model_stack(self):
        from ..dialogs.models import ModelStackDialog
        ModelStackDialog(self.bridge, self).exec()

    def refresh(self):
        self.call("data.settings", self.loaded)

    def loaded(self, value, error):
        if not value:
            return
        self.snapshot = value
        defaults = {"editor_font": "Consolas", "editor_size": 13, "editor_tab_width": 4}
        from ...research.settings import ResearchSettings
        research = {**ResearchSettings().to_dict(), **value["settings"].get("research", {})}
        for key, (control, group) in self.controls.items():
            val = (
                research[key] if group == "research" else value[group].get(key, defaults.get(key, ""))
                if group in {"settings", "params", "research"}
                else value["system_prompt" if group == "prompt" else "alias"]
            )
            if isinstance(control, QCheckBox):
                control.setChecked(bool(val))
            elif isinstance(control, QComboBox):
                control.setCurrentText(str(val))
            elif isinstance(control, (QSpinBox, QDoubleSpinBox)):
                control.setValue(float(val) if isinstance(control, QDoubleSpinBox) else int(val))
            elif isinstance(control, QPlainTextEdit):
                control.setPlainText(str(val))
            else:
                control.setText(str(val))

    def save(self):
        if not self.snapshot:
            return
        settings = {}
        params = {}
        extra = {}
        research = {}
        for key, (control, group) in self.controls.items():
            if isinstance(control, QCheckBox):
                value = control.isChecked()
            elif isinstance(control, QComboBox):
                value = control.currentText()
            elif isinstance(control, (QSpinBox, QDoubleSpinBox)):
                value = control.value()
            elif isinstance(control, QPlainTextEdit):
                value = control.toPlainText()
            else:
                value = control.text()
            (research if group == "research" else settings if group == "settings" else params if group == "params" else extra)[key] = value
        settings["research"] = research
        self.call(
            "data.save_settings",
            lambda v, e: self.statusBar().showMessage("Settings saved" if not e else e, 6000),
            chat_id=self.snapshot["chat_id"],
            settings=settings,
            params=params,
            system_prompt=extra["system_prompt"],
            alias=extra["alias"],
        )

    def reset_rag(self):
        for key, value in {
            "rag_top_k": 6,
            "rag_semantic_weight": 0.65,
            "rag_lexical_weight": 0.35,
            "rag_minimum_score": 0.08,
        }.items():
            self.controls[key][0].setValue(value)

    def install_model(self):
        name, ok = QInputDialog.getText(self, "Install local model", "Ollama model name")
        if (
            ok
            and name
            and QMessageBox.question(
                self,
                "Confirm model download",
                f"Download {name} using your local Ollama runtime? No model is downloaded unless you approve.",
            )
            == QMessageBox.StandardButton.Yes
        ):
            self.call(
                "data.pull_model",
                lambda v, e: self.statusBar().showMessage("Model installed" if not e else e, 8000),
                name=name,
                confirmed=True,
            )

    def choose_ocr(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose Tesseract executable", "", "Executable (*.exe)")
        if path:
            self.controls["ocr_executable"][0].setText(path)

    def backup(self):
        path, _ = QFileDialog.getSaveFileName(self, "Create backup", "olive-backup.zip", "ZIP (*.zip)")
        if path:
            self.call(
                "data.backup", lambda v, e: show_details(self, "Backup created", v) if v else None, path=path
            )

    def restore(self):
        path, _ = QFileDialog.getOpenFileName(self, "Restore backup", "", "ZIP (*.zip)")
        if (
            path
            and QMessageBox.warning(
                self,
                "Restore backup",
                "Replace included data with this backup? A safety backup is created first. Restart OLIVE afterwards.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            )
            == QMessageBox.StandardButton.Yes
        ):
            self.call(
                "data.restore",
                lambda v, e: show_details(self, "Restore result", v) if v else None,
                path=path,
                confirmed=True,
            )

    def export_memories(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export memories", "memories.json", "JSON (*.json)")
        if path:
            self.call("data.export", path=path, kind="memory")

    def maintenance(self):
        self.call("data.maintenance", lambda v, e: show_details(self, "Data maintenance", v) if v else None)


class DiagnosticsWindow(FeatureWindow):
    def __init__(self, manager):
        super().__init__(manager, "diagnostics")
        self.summary = ""
        layout = self.page("Diagnostics", "Local runtime and subsystem health")
        self.buttons(layout, [("Refresh", self.refresh), ("Copy diagnostic summary", self.copy)])
        self.table = QTreeWidget()
        self.table.setHeaderLabels(["Subsystem / field", "Value"])
        self.table.setColumnWidth(0, 290)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table, 1)

    def refresh(self):
        self.call("data.diagnostics", self.loaded)

    def loaded(self, value, error):
        if value is None:
            return
        # Known diagnostic fields only; never dump environment variables or settings secrets.
        rows = [
            {
                "field": key.replace("_", " ").title(),
                "value": ", ".join(map(str, val)) if isinstance(val, list) else val,
            }
            for key, val in value.items()
        ]
        self.table.clear()
        groups = {}
        for key, row in zip(value, rows):
            if key.startswith("research_") or key.startswith("web_knowledge"):
                group = "Research"
            elif "schema" in key or "integrity" in key:
                group = "Database"
            elif key.startswith("ocr_"):
                group = "OCR"
            elif "indexing" in key:
                group = "Indexing"
            elif key.startswith("ollama"):
                group = "Ollama"
            elif "model" in key:
                group = "Models"
            elif "rag" in key or "embedding" in key or "chunk" in key:
                group = "RAG"
            elif "document" in key:
                group = "Knowledge"
            elif "directory" in key or "memory_count" == key:
                group = "Storage"
            elif "agent" in key:
                group = "Agent"
            elif "docker" in key or "execution" in key or "run_session" in key:
                group = "Execution"
            else:
                group = "Application"
            if group not in groups:
                groups[group] = QTreeWidgetItem(self.table, [group])
            QTreeWidgetItem(groups[group], [row["field"], str(row["value"])])
        self.table.expandAll()
        self.summary = "\n".join(f"{r['field']}: {r['value']}" for r in rows)

    def copy(self):
        QApplication.clipboard().setText(self.summary)
