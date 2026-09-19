from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QComboBox,
    QFileDialog,
    QTableWidgetItem,
)
from ..components.common import table, populate


class PermissionDialog(QDialog):
    def __init__(self, bridge, parent=None):
        super().__init__(parent)
        self.bridge = bridge
        self.setWindowTitle("OLIVE — Permissions")
        self.resize(820, 650)
        layout = QVBoxLayout(self)
        self.rules = table(["Permission", "Decision"])
        layout.addWidget(self.rules)
        self.scopes = table(["Application scope", "Folder scope", "Permission", "Decision"])
        layout.addWidget(self.scopes)
        row = QHBoxLayout()
        for label, callback in [
            ("Add folder rule", self.add_scope),
            ("Add application rule", self.add_application_scope),
            ("Remove selected rule", self.remove_scope),
            ("Clear app approvals", self.clear),
            ("Save", self.save),
        ]:
            button = QPushButton(label)
            button.clicked.connect(callback)
            row.addWidget(button)
        layout.addLayout(row)
        self.approvals = table(["Remembered action", "Application / target"])
        layout.addWidget(self.approvals)
        bridge.call("data.permissions", self.loaded)

    def loaded(self, value, error):
        if not value:
            return
        self.values = value
        self.rules.setRowCount(len(value["permissions"]))
        for row, (permission, decision) in enumerate(sorted(value["permissions"].items())):
            self.rules.setItem(row, 0, QTableWidgetItem(permission))
            combo = QComboBox()
            combo.addItems(["allow", "ask", "deny"])
            combo.setCurrentText(decision)
            self.rules.setCellWidget(row, 1, combo)
        populate(self.scopes, value["scopes"], ["application", "path", "permission", "decision"])
        populate(self.approvals, value["trusted_actions"], ["tool", "target"])

    def add_scope(self):
        from PySide6.QtWidgets import QInputDialog

        path = QFileDialog.getExistingDirectory(self, "Scope folder")
        if not path:
            return
        permission, ok = QInputDialog.getItem(
            self, "Permission", "Rule", sorted(self.values["permissions"]), editable=False
        )
        if not ok:
            return
        decision, ok = QInputDialog.getItem(
            self, "Decision", "Access", ["ask", "allow", "deny"], editable=False
        )
        if ok:
            self.values["scopes"].append({"path": path, "permission": permission, "decision": decision})
            populate(self.scopes, self.values["scopes"], ["application", "path", "permission", "decision"])

    def add_application_scope(self):
        from PySide6.QtWidgets import QInputDialog, QMessageBox
        def loaded(applications, error=""):
            if error:
                QMessageBox.warning(self, "Application discovery", error)
                return
            options = {item["display_name"] + " (" + item["id"] + ")": item["id"] for item in applications}
            selected, ok = QInputDialog.getItem(self, "Application", "Apply this rule to", sorted(options), editable=False)
            if not ok:
                return
            permission, ok = QInputDialog.getItem(self, "Permission", "Rule", sorted(self.values["permissions"]), editable=False)
            if not ok:
                return
            decision, ok = QInputDialog.getItem(self, "Decision", "Access", ["ask", "allow", "deny"], editable=False)
            if ok:
                self.values["scopes"].append({"application": options[selected], "permission": permission, "decision": decision})
                populate(self.scopes, self.values["scopes"], ["application", "path", "permission", "decision"])
        self.bridge.call("desktop.discover_applications", loaded)

    def remove_scope(self):
        row = self.scopes.currentRow()
        if row >= 0:
            self.values["scopes"].pop(row)
            populate(self.scopes, self.values["scopes"], ["application", "path", "permission", "decision"])

    def clear(self):
        self.bridge.call(
            "data.clear_approvals", lambda v, e: self.bridge.call("data.permissions", self.loaded)
        )

    def save(self):
        permissions = {
            self.rules.item(row, 0).text(): self.rules.cellWidget(row, 1).currentText()
            for row in range(self.rules.rowCount())
        }
        self.bridge.call(
            "data.save_permissions",
            lambda v, e: self.accept() if not e else None,
            permissions=permissions,
            scopes=self.values["scopes"],
        )
