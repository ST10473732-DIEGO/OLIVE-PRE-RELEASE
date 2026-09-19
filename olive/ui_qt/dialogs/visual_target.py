"""Explicit visual fallback review; model coordinates never trigger input on display."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QPainter, QPen, QColor
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton


class VisualTargetDialog(QDialog):
    def __init__(self, bridge, result, parent=None):
        super().__init__(parent)
        self.setWindowTitle("OLIVE - Review visual target")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(result["target_label"]))
        capture = result["capture"]
        pixmap = QPixmap(capture["path"])
        painter = QPainter(pixmap)
        painter.setPen(QPen(QColor("#83b9ff"), 3))
        bounds = result["bounds"]
        painter.drawRect(bounds["left"], bounds["top"], bounds["right"] - bounds["left"], bounds["bottom"] - bounds["top"])
        painter.end()
        image = QLabel()
        image.setPixmap(pixmap.scaled(900, 600, Qt.AspectRatioMode.KeepAspectRatio))
        layout.addWidget(image)
        expected = QLineEdit()
        expected.setPlaceholderText("Exact visible control expected after the click")
        layout.addWidget(expected)
        status = QLabel("One reviewed click. Changed pixels, lost focus or missing verification stop the action.")
        status.setWordWrap(True)
        layout.addWidget(status)
        button = QPushButton("Review click permissions")
        button.setEnabled(result["target_found"] and result["confidence"] >= .85)
        layout.addWidget(button)
        def completed(value, error=""):
            status.setText(error or "Expected application state observed")
        def perform():
            button.setEnabled(False)
            bridge.call("desktop.visual_click", completed, capture_id=result["capture_id"], expected=expected.text())
        button.clicked.connect(perform)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        layout.addWidget(close)
