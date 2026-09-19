from PySide6.QtWidgets import QDialog, QVBoxLayout, QComboBox, QPushButton, QLabel


class MediaDialog(QDialog):
    def __init__(self, bridge, parent=None):
        super().__init__(parent)
        self.bridge = bridge
        self.setWindowTitle("OLIVE — System media controls")
        self.resize(620, 320)
        layout = QVBoxLayout(self)
        self.apps = QComboBox()
        layout.addWidget(self.apps)
        for label, action in (("Play", "play"), ("Pause", "pause"), ("Next", "next"), ("Previous", "previous")):
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, command=action: self.run(command))
            layout.addWidget(button)
        self.status = QLabel("Reading available media sessions…")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        bridge.call("desktop.media_sessions", self.loaded)

    def loaded(self, result, error):
        self.status.setText(error or "Select an active media application")
        for item in result or []:
            self.apps.addItem(" · ".join(filter(None, (item["application_id"], item["state"], item.get("title", "")))), item["application_id"])

    def run(self, action):
        if self.apps.currentData():
            self.bridge.call("desktop.media_action", lambda result, error: self.status.setText(error or "Playback state verified"),
                             application_id=self.apps.currentData(), action=action)
