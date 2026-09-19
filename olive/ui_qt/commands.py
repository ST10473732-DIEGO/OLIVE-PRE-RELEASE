from PySide6.QtWidgets import QDialog, QVBoxLayout, QLineEdit, QListWidget, QListWidgetItem
from PySide6.QtCore import Qt


class CommandPalette(QDialog):
    def __init__(self, manager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.setWindowTitle("OLIVE — Commands")
        self.resize(540, 430)
        layout = QVBoxLayout(self)
        self.query = QLineEdit()
        self.query.setPlaceholderText("Type a command…")
        self.results = QListWidget()
        layout.addWidget(self.query)
        layout.addWidget(self.results)
        self.commands = [
            ("Open " + f.title, lambda fid=f.id: manager.open(fid)) for f in manager.registry.list()
        ]
        self.commands.append(("New Chat", lambda: manager.open("chat").new_chat()))
        self.commands.append(("Open Project", lambda: manager.open("projects")))
        self.commands.append(("New Project", lambda: manager.open("projects").new_project()))
        if manager.navigation.current in manager.POPOUT_FEATURES:
            feature = manager.navigation.current
            self.commands.append(("Pop out " + manager.registry.get(feature).title,
                                  lambda fid=feature: manager.popout(fid)))
        self.query.textChanged.connect(self.filter)
        self.query.returnPressed.connect(self.activate)
        self.results.itemActivated.connect(self.activate)
        self.filter("")

    def filter(self, text):
        self.results.clear()
        for index, (title, _) in enumerate(self.commands):
            if text.casefold() in title.casefold():
                item = QListWidgetItem(title)
                item.setData(Qt.ItemDataRole.UserRole, index)
                self.results.addItem(item)
        self.results.setCurrentRow(0)

    def activate(self, *args):
        item = self.results.currentItem()
        if item:
            self.accept()
            self.commands[item.data(Qt.ItemDataRole.UserRole)][1]()
