"""Task and evidence workspace. All work is dispatched to the shared runtime."""

import json
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QInputDialog,
    QPlainTextEdit,
    QSplitter,
    QTabWidget,
    QTextBrowser,
    QWidget,
    QVBoxLayout,
)
from .base import FeatureWindow
from ..components.common import table, populate, selected


class ResearchMarkdown(QTextBrowser):
    def loadResource(self, kind, url):
        return None


class ResearchWindow(FeatureWindow):
    def __init__(self, manager):
        super().__init__(manager, "research")
        self.session = None
        self.context = {}
        self.pending_project = None
        self.defaults_loaded = False
        layout = self.page("Research", "Ask a question. Compare sources. Keep the evidence.")
        self.question = QLineEdit()
        self.question.setPlaceholderText("What would you like OLIVE to investigate?")
        self.question.setAccessibleName("Research question")
        layout.addWidget(self.question)
        row = QHBoxLayout()
        self.project = QComboBox()
        self.project.addItem("Global research", None)
        self.depth = QComboBox()
        self.depth.addItems(["Quick", "Standard", "Deep"])
        self.depth.setCurrentText("Standard")
        row.addWidget(QLabel("Project"))
        row.addWidget(self.project, 1)
        row.addWidget(QLabel("Depth"))
        row.addWidget(self.depth)
        layout.addLayout(row)
        self.buttons(
            layout,
            [
                ("New Research", self.new),
                ("Research", self.start),
                ("Pause", lambda: self.call("research.pause")),
                ("Resume", self.resume),
                ("Cancel", lambda: self.call("research.cancel")),
                ("Save source to Knowledge", self.save_source),
                ("Save report to Project", self.save_report),
                ("Learn website", self.learn_website),
            ],
        )
        self.activity = QLabel("Ready · Sources are saved permanently only after approval.")
        self.activity.setWordWrap(True)
        self.activity.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.activity)
        split = QSplitter()
        left = QWidget()
        sidebar = QVBoxLayout(left)
        sidebar.addWidget(QLabel("Research history"))
        self.history = QListWidget()
        self.history.itemClicked.connect(self.open_history)
        sidebar.addWidget(self.history)
        sidebar.addWidget(QLabel("Plan"))
        self.plan = QPlainTextEdit()
        self.plan.setReadOnly(True)
        sidebar.addWidget(self.plan)
        split.addWidget(left)
        tabs = QTabWidget()
        self.findings = ResearchMarkdown()
        self.findings.setOpenLinks(False)
        self.findings.setOpenExternalLinks(False)
        self.findings.anchorClicked.connect(self.inspect_citation)
        tabs.addTab(self.findings, "Findings")
        source_page = QWidget()
        source_layout = QVBoxLayout(source_page)
        self.sources = table(["Title", "Domain", "State", "Published"])
        self.sources.itemSelectionChanged.connect(self.show_source)
        source_layout.addWidget(self.sources, 1)
        self.evidence = QPlainTextEdit()
        self.evidence.setReadOnly(True)
        source_layout.addWidget(self.evidence, 1)
        self.buttons(source_layout, [("Open externally", self.open_external)])
        tabs.addTab(source_page, "Sources / Evidence")
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        tabs.addTab(self.details, "Details")
        self.tabs = tabs
        menu = self.menuBar().addMenu("Research")
        menu.addAction("Downloads", self.downloads)
        menu.addAction("Save all used sources to Knowledge", self.save_used_sources)
        menu.addAction("Save selected findings to Project", self.save_findings)
        menu.addAction("Clear temporary page cache", lambda: self.call("research.clear_cache"))
        split.addWidget(tabs)
        split.setSizes([280, 800])
        layout.addWidget(split, 1)

    def refresh(self):
        self.call("research.history", self.loaded_history)
        self.call("data.projects", self.loaded_projects)
        if not self.defaults_loaded:
            self.call("research.preferences", self.loaded_preferences)

    def loaded_preferences(self, value, error=""):
        if value:
            if self.session is None:
                self.depth.setCurrentText(value["depth"])
            self.defaults_loaded = True

    def loaded_projects(self, values, error=""):
        if values is None:
            return
        current = self.pending_project or self.project.currentData()
        self.project.clear()
        self.project.addItem("Global research", None)
        for value in values:
            self.project.addItem(value["title"], value["id"])
        self.project.setCurrentIndex(max(0, self.project.findData(current)))
        self.pending_project = None

    def loaded_history(self, values, error=""):
        if values is None:
            return
        self.history.clear()
        for value in values:
            item = QListWidgetItem(
                f"{value['question']}\n{value['status']} · {value['started_at'][:10]} · {len(value['sources'])} sources"
            )
            item.setData(Qt.ItemDataRole.UserRole, value["id"])
            self.history.addItem(item)

    def open_history(self, item):
        self.call("research.get", self.render, session_id=item.data(Qt.ItemDataRole.UserRole))

    def new(self):
        self.session = None
        self.context = {}
        self.question.clear()
        self.findings.clear()
        self.plan.clear()
        self.sources.setRowCount(0)
        self.evidence.clear()
        self.details.clear()
        self.activity.setText("Ready for a new investigation")
        self.question.setFocus()

    def prefill(self, question, project_id=None, context=None):
        self.new()
        self.question.setText(question[:4000])
        self.context = context or {}
        self.pending_project = project_id
        self.project.setCurrentIndex(max(0, self.project.findData(project_id)))

    def start(self):
        if self.question.text().strip():
            self.call(
                "research.start",
                self.render,
                question=self.question.text(),
                project_id=self.project.currentData(),
                context=self.context,
                depth=self.depth.currentText(),
            )

    def resume(self):
        if self.session:
            self.call("research.resume", self.render, session_id=self.session["id"])

    def render(self, value, error=""):
        if error:
            self.activity.setText(error)
        if not value:
            return
        self.session = value
        self.depth.setCurrentText(value["settings"].get("depth", "Standard"))
        self.question.setText(value["question"])
        self.activity.setText(
            f"{value['status'].title()} · {value.get('activity', '')} · "
            f"{len(value['queries'])} searches · {len(value['evidence'])} evidence items"
        )
        self.plan.setPlainText("\n".join(value.get("plan", {}).get("subquestions", [])))
        self.findings.setMarkdown(value.get("final_report") or "Research findings will appear here.")
        populate(self.sources, value["sources"], ["title", "domain", "status", "publication_date"])
        self.details.setPlainText(
            json.dumps(
                {"error": value.get("error"), "queries": value["queries"], "settings": value["settings"]},
                indent=2,
            )
        )

    def on_event(self, topic, value):
        super().on_event(topic, value)
        if topic == "research":
            self.render(value)
            if value["status"] in {"completed", "paused", "failed", "cancelled"}:
                self.call("research.history", self.loaded_history)

    def show_source(self):
        source = selected(self.sources)
        if not source or not self.session:
            return
        quotes = [e["quote"] for e in self.session["evidence"] if e["source_id"] == source["id"]]
        self.evidence.setPlainText(
            "\n\n".join(
                [
                    source["title"],
                    source["url"],
                    f"Retrieved: {source.get('retrieved_at', '')}\nPublished: {source.get('publication_date') or 'Unknown'}",
                "Untrusted source material",
                f"Author: {source.get('author') or 'Unknown'} · Updated: {source.get('updated_date') or 'Unknown'}",
                json.dumps(source.get("quality", {}), indent=2),
                    *quotes,
                ]
            )
        )

    def inspect_citation(self, url):
        if self.session:
            for index, source in enumerate(self.session["sources"]):
                if url.toString() == source["url"]:
                    self.sources.selectRow(index)
                    self.tabs.setCurrentIndex(1)
                    break

    def open_external(self):
        source = selected(self.sources)
        if source and source["url"].startswith(("https://", "http://")):
            QDesktopServices.openUrl(QUrl(source["url"]))

    def save_source(self):
        source = selected(self.sources)
        if source and self.session:
            self.call("research.save_sources", session_id=self.session["id"], source_ids=[source["id"]])
        else:
            self.tabs.setCurrentIndex(1)
            self.statusBar().showMessage("Select a read source first", 6000)

    def save_report(self):
        if (
            self.session
            and self.project.currentData()
            and QMessageBox.question(
                self, "Save research report", "Save this report to the selected project?"
            )
            == QMessageBox.StandardButton.Yes
        ):
            self.call(
                "research.save_report",
                session_id=self.session["id"],
                project_id=self.project.currentData(),
                approved=True,
            )

    def save_used_sources(self):
        if self.session:
            source_ids = [
                source["id"]
                for source in self.session["sources"]
                if source["status"] in {"evidence", "saved"}
                and source["url"].startswith(("https://", "http://"))
            ]
            if source_ids:
                self.call("research.save_sources", session_id=self.session["id"], source_ids=source_ids)

    def save_findings(self):
        if not self.session or not self.project.currentData() or not self.session["findings"]:
            self.statusBar().showMessage("Choose a project and a completed report first", 6000)
            return
        labels = [f"{index + 1}. {finding['text']}" for index, finding in enumerate(self.session["findings"])]
        choice, ok = QInputDialog.getItem(
            self, "Save selected finding", "Choose a finding to save to the project", labels, editable=False
        )
        if ok:
            self.call(
                "research.save_report",
                session_id=self.session["id"],
                project_id=self.project.currentData(),
                approved=True,
                finding_indices=[labels.index(choice)],
            )

    def learn_website(self):
        from ..dialogs.web_knowledge import WebKnowledgeDialog

        WebKnowledgeDialog(self.manager, self).exec()

    def downloads(self):
        from ..dialogs.research_downloads import ResearchDownloadsDialog

        ResearchDownloadsDialog(self.bridge, self).exec()
