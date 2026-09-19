"""Native inspector for user-directed generic application control."""

from PySide6.QtWidgets import QLabel, QTreeWidgetItem, QDialog, QVBoxLayout, QFileDialog
from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt
from .base import FeatureWindow


class DesktopWindow(FeatureWindow):
    def __init__(self, manager):
        super().__init__(manager, "desktop")
        from ..components.desktop_workspace import build
        build(self)
        self.snapshot = {}
        self.browser_mode = False
        self.browser_snapshot = {}
        self.last_download = None

    def inspect_vision(self):
        def observed(result, error=""):
            if error:
                self.state.setText(error)
                return
            self.state.setText("Visual observation: " + str(result.get("visible_state", result)))
            if result.get("target_found") and result.get("capture"):
                from ..dialogs.visual_target import VisualTargetDialog
                VisualTargetDialog(self.bridge, result, self).exec()
        self.call("desktop.vision_observe", observed,
                  question=self.objective.text().strip() or "Describe the visible application state")

    def verify_visual_label(self):
        if not self.expected.text().strip():
            self.state.setText("Enter the expected visible button label in Verify first")
            return
        def observed(result, error=""):
            self.state.setText(error or ("Captured label " + ("verified: " if result["verified"] else "did not match: ") + result["observed_label"]))
        self.call("desktop.vision_verify_label", observed, expected=self.expected.text().strip())

    def applications(self):
        from ..dialogs.applications import ApplicationsDialog
        ApplicationsDialog(self.bridge, self).exec()

    def media_controls(self):
        from ..dialogs.media import MediaDialog
        MediaDialog(self.bridge, self).exec()

    def clipboard_controls(self):
        from ..dialogs.clipboard import ClipboardDialog
        ClipboardDialog(self.bridge, self).exec()

    def review_consequence(self):
        from ..dialogs.desktop_consequence import DesktopConsequenceDialog
        item = self.controls.currentItem()
        if item and not self.browser_mode:
            target = {"runtime_id": item.data(0, Qt.ItemDataRole.UserRole)["runtime_id"]}
            DesktopConsequenceDialog(self.bridge, self.snapshot.get("observation", {}).get("controls", []), target, self).exec()

    def create_plan(self):
        def planned(steps, error=""):
            if error:
                self.state.setText(error)
                return
            self.state.setText("Plan: " + " → ".join(step["application"] + ": " + step["action"] for step in steps))
        self.call("desktop.plan", planned, objective=self.objective.text())

    def show_screenshot(self, result, error=""):
        if error:
            self.state.setText(error)
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("OLIVE — Authorized window screenshot")
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(result["window"]["application"]))
        label = QLabel()
        label.setPixmap(QPixmap(result["path"]).scaled(1000, 700, Qt.AspectRatioMode.KeepAspectRatio))
        layout.addWidget(label)
        dialog.exec()

    def open_browser(self):
        self.call("desktop.browser_launch", self.render_tabs)

    def render_tabs(self, tabs, error=""):
        if error:
            self.state.setText(error)
            return
        self.tabs.clear()
        for tab in tabs:
            self.tabs.addItem(tab["title"] or tab["url"], tab["id"])

    def review_message(self):
        from ..dialogs.browser_message import BrowserMessageDialog
        if self.browser_mode:
            BrowserMessageDialog(self.bridge, self.browser_snapshot.get("controls", []), self).exec()

    def review_browser_dialog(self):
        from PySide6.QtWidgets import QMessageBox
        def loaded(result, error=""):
            if error or not result.get("pending"):
                self.state.setText(error or "No browser dialog is pending")
                return
            dialog = QMessageBox(self)
            dialog.setWindowTitle("OLIVE - Browser dialog")
            dialog.setTextFormat(Qt.TextFormat.PlainText)
            dialog.setText(result["message"])
            dismiss = dialog.addButton("Review dismissal", QMessageBox.ButtonRole.ActionRole)
            dialog.addButton("Leave open", QMessageBox.ButtonRole.RejectRole)
            dialog.exec()
            if dialog.clickedButton() is dismiss:
                self.call("desktop.browser_dialog", lambda result, error: self.state.setText(error or "Browser dialog dismissed"), dismiss=True)
        self.call("desktop.browser_dialog", loaded)

    def upload_file(self):
        item = self.controls.currentItem()
        if not self.browser_mode or not item:
            self.state.setText("Inspect the browser and select its upload control first")
            return
        path, _ = QFileDialog.getOpenFileName(self, "Select an attachment for reviewed upload")
        if path:
            self.call("desktop.browser_upload", self.render_browser,
                      target_id=item.data(0, Qt.ItemDataRole.UserRole)["id"], path=path)

    def download_file(self):
        item = self.controls.currentItem()
        if self.browser_mode and item:
            self.call("desktop.browser_download", self.downloaded, target_id=item.data(0, Qt.ItemDataRole.UserRole)["id"])

    def downloaded(self, result, error=""):
        if error:
            self.state.setText(error)
        else:
            self.last_download = result["download"]
            self.state.setText("Quarantined: " + self.last_download["filename"] + " · " + str(self.last_download["size"]) + " bytes")

    def save_download(self):
        if self.last_download:
            path, _ = QFileDialog.getSaveFileName(self, "Save quarantined file", self.last_download["filename"])
            if path:
                self.call("desktop.save_download", lambda result, error: self.state.setText(error or "File saved; it remains untrusted"),
                          download_id=self.last_download["id"], destination=path)

    def navigate_browser(self):
        if self.tabs.currentData():
            self.call("desktop.browser_navigate", self.render_browser, tab_id=self.tabs.currentData(), url=self.url.text())

    def inspect_browser(self):
        if self.tabs.currentData():
            self.call("desktop.browser_observe", self.render_browser, tab_id=self.tabs.currentData())

    def render_browser(self, result, error=""):
        if error:
            self.state.setText(error)
            return
        self.browser_mode = True
        self.browser_snapshot = result
        self.controls.clear()
        self.state.setText(result.get("message") or "Interactive browser · " + result["title"])
        for control in result["controls"]:
            item = QTreeWidgetItem([control["name"], control["role"] or control["type"], "click / fill / select / scroll", ""])
            item.setData(0, Qt.ItemDataRole.UserRole, control)
            self.controls.addTopLevelItem(item)

    def refresh(self):
        self.call("desktop.status", self.render)

    def configure(self):
        settings = dict(self.snapshot.get("settings", {}))
        settings["enabled"] = self.enabled.isChecked()
        self.call("desktop.configure", self.render, settings=settings)

    def list_windows(self):
        def loaded(items, error=""):
            if error:
                self.state.setText(error)
                return
            self.windows.clear()
            for item in items:
                self.windows.addItem(item["application"] + " — " + item["title"], item["id"])
        self.call("desktop.list_windows", loaded)

    def inspect(self):
        if self.windows.currentData():
            self.call("desktop.inspect", self.render, window_id=self.windows.currentData())

    def render(self, value, error=""):
        if error:
            self.state.setText(error)
            return
        if not value:
            return
        self.snapshot = value
        self.browser_mode = False
        self.enabled.setChecked(value["settings"]["enabled"])
        session = value.get("session") or {}
        phases = [item["operation"] + " - " + item["status"] for item in value.get("workflow_phases", [])]
        current = session.get("current_action", "")
        self.phases.setText("\n".join([*phases[-8:], current] if current else phases[-8:]))
        self.state.setText("STOPPED" if value["stopped"] else
                           " · ".join(str(session.get(key, "")) for key in ("application", "status", "verification")))
        self.controls.clear()
        for control in value.get("observation", {}).get("controls", []):
            if control.get("password"):
                continue
            item = QTreeWidgetItem([control.get("name", ""), control.get("control_type", ""),
                ", ".join(control.get("actions", [])), "Selected" if control.get("selected") else ""])
            item.setData(0, Qt.ItemDataRole.UserRole, control)
            self.controls.addTopLevelItem(item)

    def perform(self):
        item = self.controls.currentItem()
        if not item:
            self.state.setText("Select a control first")
            return
        control = item.data(0, Qt.ItemDataRole.UserRole)
        action = self.action.currentText()
        if self.browser_mode:
            self.call("desktop.browser_action", self.render_browser, target_id=control["id"], action=action,
                      value=self.text.text(), expected=self.expected.text())
            return
        arguments = {"text": self.text.text()} if action in {"set_text", "search"} else {"direction": "down"} if action == "scroll" else {}
        expected = {"runtime_id": control["runtime_id"], "value": self.text.text()} if action == "set_text" else {"name": self.expected.text()}
        if action != "set_text" and not self.expected.text().strip():
            self.state.setText("Specify the expected visible control after this action")
            return
        self.call("desktop.perform", self.render, action=action, target={"runtime_id": control["runtime_id"]},
                  arguments=arguments, expected=expected)

    def on_event(self, topic, value):
        super().on_event(topic, value)
        if topic == "desktop":
            self.render(value)
