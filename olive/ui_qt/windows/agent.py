from PySide6.QtWidgets import QPlainTextEdit, QComboBox, QLabel, QProgressBar, QTabWidget
from .base import FeatureWindow
from ..components.common import table, populate, selected, show_details


class AgentWindow(FeatureWindow):
    def __init__(self, manager):
        super().__init__(manager, "agent")
        self.current = {}
        layout = self.page("Agent", "Describe an outcome. OLIVE plans and acts through your permission rules.")
        self.workspace = QComboBox()
        self.workspace.setAccessibleName("Agent workspace")
        layout.addWidget(self.workspace)
        self.project = QComboBox()
        self.project.setAccessibleName("Agent project")
        layout.addWidget(self.project)
        self.objective = QPlainTextEdit()
        self.objective.setPlaceholderText("What should OLIVE accomplish?")
        self.objective.setMaximumHeight(120)
        layout.addWidget(self.objective)
        self.buttons(
            layout,
            [
                ("Start task", self.run),
                ("Pause", lambda: self.call("agent.pause")),
                ("Resume", lambda: self.resume()),
                ("Cancel", lambda: self.call("agent.cancel")),
                ("View details", lambda: show_details(self, "Task details", self.current)),
                ("Action history", self.actions),
                ("Show changes", self.changes),
            ],
        )
        self.state = QLabel("Ready")
        layout.addWidget(self.state)
        self.progress = QProgressBar()
        layout.addWidget(self.progress)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        self.plan = table(["Step", "Tool", "State"])
        self.tabs.addTab(self.plan, "Plan")
        self.activity = table(["Tool", "Result"])
        self.tabs.addTab(self.activity, "Activity")
        self.files = QPlainTextEdit()
        self.files.setReadOnly(True)
        self.tabs.addTab(self.files, "Changed files")
        self.history = table(["Objective", "State", "Validation", "Updated"])
        self.tabs.addTab(self.history, "Task history")
        self.history.doubleClicked.connect(self.history_details)

    def refresh(self):
        self.call("data.workspaces", self.workspaces)
        self.call("data.projects", self.projects)
        self.call("agent.history", self.render_history)

    def workspaces(self, values, error):
        if values is None:
            return
        current = self.workspace.currentData()
        self.workspace.clear()
        self.workspace.addItem("No workspace", None)
        for value in values:
            self.workspace.addItem(value["title"], value["id"])
        self.workspace.setCurrentIndex(max(0, self.workspace.findData(current)))

    def projects(self, values, error):
        if values is None:
            return
        current = self.project.currentData()
        self.project.clear()
        self.project.addItem("No project", None)
        for value in values:
            self.project.addItem(value["title"], value["id"])
        self.project.setCurrentIndex(max(0, self.project.findData(current)))

    def resume(self):
        value = selected(self.history)
        self.call("agent.resume", self.finished, task_id=value["id"] if value else None)

    def render_history(self, values, error):
        if values is not None:
            populate(self.history, values, ["user_request", "state", "validation_status", "updated_at"])

    def run(self):
        self.state.setText("Planning…")
        self.progress.setRange(0, 0)
        self.call(
            "agent.run",
            self.finished,
            request=self.objective.toPlainText(),
            workspace_id=self.workspace.currentData(),
            project_id=self.project.currentData(),
        )

    def finished(self, value, error):
        self.progress.setRange(0, 100)
        if value:
            self.render(value)
        elif error:
            self.state.setText(error)
        self.refresh()

    def render(self, value):
        self.current = value
        self.state.setText(
            f"{value['state'].title()}   ·   Implementation: {value['implementation_status']}   ·   Validation: {value['validation_status']}"
        )
        populate(self.plan, value["plan"], ["description", "tool_name", "state"])
        calls = [{"tool": call["tool"], "result": call["result"]["summary"]} for call in value["tool_calls"]]
        populate(self.activity, calls, ["tool", "result"])
        self.files.setPlainText("\n".join(value["files_changed"]) or "No changed files recorded")
        self.progress.setRange(0, 100)
        self.progress.setValue(
            int(100 * sum(s["state"] == "completed" for s in value["plan"]) / max(1, len(value["plan"])))
        )

    def on_event(self, topic, value):
        super().on_event(topic, value)
        if topic == "agent":
            self.render(value)
        elif topic == "workspaces":
            self.workspaces(value, "")

    def history_details(self):
        value = selected(self.history)
        if value:
            show_details(self, "Recorded task", value)

    def actions(self):
        self.call(
            "agent.actions", lambda v, e: show_details(self, "Action history", v) if v is not None else None
        )

    def changes(self):
        if self.workspace.currentData():
            self.call(
                "studio.git",
                lambda v, e: show_details(self, "Workspace changes", v) if v else None,
                workspace_id=self.workspace.currentData(),
                action="diff",
            )
