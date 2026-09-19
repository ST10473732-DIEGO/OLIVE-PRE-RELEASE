from ..icons import icon
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QLabel, QPushButton, QGridLayout


class FeatureWindow(QMainWindow):
    def __init__(self, manager, feature_id):
        super().__init__()
        self.manager = manager
        self.bridge = manager.bridge
        self.feature_id = feature_id
        self.setWindowTitle(f"OLIVE — {manager.registry.get(feature_id).title}")
        self.setWindowIcon(icon(manager.registry.get(feature_id).icon))
        self.resize(1120, 800)
        self.setMinimumSize(760, 540)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        # Global navigation belongs to the shell; feature menus remain local.
        self.bridge.event.connect(self.on_event)
        self.statusBar().showMessage("Local-first · Ollama")

    def on_event(self, topic, value):
        if topic == "notification":
            self.statusBar().showMessage(value["message"], 10000)

    def closeEvent(self, event):
        if not self.can_close():
            event.ignore()
            return
        self.manager.save_window(self)
        event.accept()

    def can_close(self, exiting=False):
        return True

    def page(self, title, subtitle=""):
        page = QWidget()
        page.setObjectName("page")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)
        label = QLabel(title)
        label.setObjectName("title")
        layout.addWidget(label)
        if subtitle:
            label = QLabel(subtitle)
            label.setObjectName("subtitle")
            label.setWordWrap(True)
            layout.addWidget(label)
        self.setCentralWidget(page)
        return layout

    def buttons(self, layout, actions):
        row = QGridLayout()
        for index, (title, callback) in enumerate(actions):
            button = QPushButton(title)
            button.clicked.connect(callback)
            row.addWidget(button, index // 4, index % 4)
        layout.addLayout(row)
        return row

    def call(self, operation, callback=None, **arguments):
        return self.bridge.call(operation, callback, **arguments)
