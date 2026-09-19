from PySide6.QtWidgets import QDialog, QFormLayout, QCheckBox, QComboBox, QSpinBox, QPushButton, QLabel
from ...desktop.settings import DEFAULTS


class DesktopSettingsDialog(QDialog):
    def __init__(self, bridge, parent=None):
        super().__init__(parent)
        self.bridge = bridge
        self.setWindowTitle("OLIVE — Desktop Control settings")
        self.resize(520, 460)
        form = QFormLayout(self)
        self.controls = {}
        for key, default in DEFAULTS.items():
            if type(default) is bool:
                widget = QCheckBox()
            elif type(default) is int:
                widget = QSpinBox()
                widget.setRange(1, 100)
            else:
                widget = QComboBox()
                widget.addItems(["deny", "ask", "allow"] if key.endswith("policy") else
                                ["Ctrl+Alt+Escape", ""] if key == "emergency_shortcut" else ["pause"])
            self.controls[key] = widget
            form.addRow(key.replace("_", " ").title(), widget)
        form.addRow(QLabel("App-scoped permissions remain authoritative. Ctrl+Alt+Escape is available when Windows accepts the hotkey registration."))
        button = QPushButton("Save")
        button.clicked.connect(self.save)
        form.addRow(button)
        self.status = QLabel()
        self.status.setWordWrap(True)
        form.addRow(self.status)
        bridge.call("desktop.status", self.load)

    def load(self, result, error=""):
        if error:
            self.status.setText(error)
            return
        for key, value in result["settings"].items():
            widget = self.controls[key]
            if isinstance(widget, QCheckBox):
                widget.setChecked(value)
            elif isinstance(widget, QSpinBox):
                widget.setValue(value)
            else:
                widget.setCurrentText(value)

    def save(self):
        value = {key: widget.isChecked() if isinstance(widget, QCheckBox) else widget.value()
                 if isinstance(widget, QSpinBox) else widget.currentText() for key, widget in self.controls.items()}
        def saved(result, error):
            if error:
                self.status.setText(error)
            else:
                self.accept()
        self.bridge.call("desktop.configure", saved, settings=value)
