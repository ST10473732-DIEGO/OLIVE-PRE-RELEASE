from PySide6.QtWidgets import QFrame, QGridLayout, QVBoxLayout, QLabel, QPushButton, QScrollArea, QWidget, QLineEdit, QHBoxLayout
from PySide6.QtCore import QTimer
from .base import FeatureWindow
from ..icons import icon


class HomeWindow(FeatureWindow):
    def __init__(self, manager):
        super().__init__(manager, "home")
        layout = self.page("OLIVE", "Your private workspace for ideas, knowledge and building.")
        self.system = QLabel("Starting local services…")
        self.system.setObjectName("subtitle")
        layout.addWidget(self.system)
        self.setup_hint = QLabel()
        self.setup_hint.setWordWrap(True)
        self.setup_hint.setVisible(False)
        layout.addWidget(self.setup_hint)
        composer_row = QHBoxLayout()
        self.composer = QLineEdit()
        self.composer.setPlaceholderText("What would you like to do?")
        self.composer.setAccessibleName("Ask OLIVE")
        submit = QPushButton("Ask OLIVE")
        submit.setObjectName("primary")
        submit.clicked.connect(self.submit_request)
        self.composer.returnPressed.connect(self.submit_request)
        composer_row.addWidget(self.composer, 1)
        composer_row.addWidget(submit)
        layout.addLayout(composer_row)
        host = QWidget()
        host.setObjectName("page")
        self.grid = QGridLayout(host)
        self.grid.setSpacing(16)
        self.cards = []
        for feature in manager.registry.list():
            if feature.id == "home" or feature.priority >= 90:
                continue
            card = QFrame()
            card.setObjectName("card")
            box = QVBoxLayout(card)
            box.setContentsMargins(22, 22, 22, 22)
            title = QLabel(feature.title)
            title.setStyleSheet("font-size:20px;font-weight:600")
            description = QLabel(feature.description)
            description.setWordWrap(True)
            description.setObjectName("subtitle")
            button = QPushButton("Open " + feature.title)
            button.setIcon(icon(feature.icon))
            button.clicked.connect(lambda checked=False, fid=feature.id: manager.open(fid))
            box.addWidget(title)
            box.addWidget(description)
            box.addStretch()
            box.addWidget(button)
            card.setMinimumHeight(180)
            self.cards.append(card)
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setWidget(host)
        layout.addWidget(area, 1)
        self.buttons(
            layout,
            [
                (f.title, lambda checked=False, fid=f.id: manager.open(fid))
                for f in manager.registry.list()
                if f.priority >= 90
            ],
        )
        self.timer = QTimer(self)
        self.timer.timeout.connect(lambda: self.call("data.status", self.render_status))
        self.timer.start(3000)
        self.reflow()

    def submit_request(self):
        text = self.composer.text().strip()
        if text:
            self.composer.clear()
            self.manager.open("chat")
            self.call("interaction.submit", text=text)

    def render_status(self, value, error=""):
        if value:
            self.system.setText(
                f"OLIVE {value['version']}   ·   {value['ollama']}   ·   Agent {value['agent']}   ·   {value['indexing']} indexing jobs"
            )
            message = ""
            if value.get("chat_models") == 0:
                message = (
                    "No chat model is available. Start Ollama, then refresh installed models in Settings."
                )
            elif not value.get("embedding_available", True):
                message = "Knowledge search is using lexical retrieval. You can select an installed embedding model in Settings."
            self.setup_hint.setText(message)
            self.setup_hint.setVisible(bool(message))

    def on_event(self, topic, value):
        super().on_event(topic, value)
        if topic == "status":
            self.render_status(value)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "cards"):
            self.reflow()

    def reflow(self):
        columns = 3 if self.width() >= 1000 else 2
        for index, card in enumerate(self.cards):
            self.grid.addWidget(card, index // columns, index % columns)
