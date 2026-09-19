"""User-selected application catalog; no fixed list of adapters is required."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLineEdit, QListWidget, QListWidgetItem, QPushButton, QLabel


class ApplicationsDialog(QDialog):
    def __init__(self, bridge, parent=None):
        super().__init__(parent)
        self.bridge = bridge
        self.setWindowTitle("OLIVE — Installed applications")
        self.resize(600, 520)
        layout = QVBoxLayout(self)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Find an installed application")
        layout.addWidget(self.search)
        self.items = QListWidget()
        layout.addWidget(self.items)
        self.alias = QLineEdit()
        self.alias.setPlaceholderText("Optional alias, such as music or browser")
        layout.addWidget(self.alias)
        save = QPushButton("Save alias for selected application")
        save.clicked.connect(self.save_alias)
        layout.addWidget(save)
        launch = QPushButton("Open selected application")
        launch.clicked.connect(self.launch)
        layout.addWidget(launch)
        self.status = QLabel("Reading installed application registrations…")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.values = []
        self.search.textChanged.connect(self.filter)
        bridge.call("desktop.discover_applications", self.loaded)

    def loaded(self, values, error):
        self.values = values or []
        self.status.setText(error or str(len(self.values)) + " applications found")
        self.filter(self.search.text())

    def filter(self, query):
        self.items.clear()
        for app in self.values:
            if query.casefold() in app["display_name"].casefold():
                item = QListWidgetItem(app["display_name"])
                item.setData(Qt.ItemDataRole.UserRole, app["id"])
                self.items.addItem(item)

    def selected(self):
        item = self.items.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def save_alias(self):
        if self.selected():
            self.bridge.call("desktop.application_alias", lambda result, error: self.status.setText(error or "Alias saved"),
                             alias=self.alias.text(), application_id=self.selected())

    def launch(self):
        if self.selected():
            self.status.setText("Opening and verifying application…")
            self.bridge.call("desktop.open_application", self.launched, application_id=self.selected())

    def launched(self, result, error):
        self.status.setText(error or ("Application window verified" if result["verified"] else result["message"]))
