"""Harmless custom-painted target with no UIA invocation pattern or OLIVE adapter."""
import sys
from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QPainter, QColor
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel


class PaintedTarget(QWidget):
    def __init__(self, label):
        super().__init__()
        self.label = label
        self.setMinimumHeight(150)
        self.setAccessibleName("Custom painted area")

    def target(self):
        return QRect(self.width() // 2 - 100, 45, 200, 60)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#f4f4f4"))
        painter.fillRect(self.target(), QColor("#3467ad"))
        painter.setPen(QColor("white"))
        painter.drawText(self.target(), Qt.AlignmentFlag.AlignCenter, "Preview")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.target().contains(event.position().toPoint()):
            self.label.setText("Visual interaction verified")


app = QApplication(sys.argv)
window = QWidget()
window.setWindowTitle("OLIVE Visual Fallback Acceptance")
layout = QVBoxLayout(window)
label = QLabel("Waiting for reviewed visual input")
layout.addWidget(label)
layout.addWidget(PaintedTarget(label))
window.resize(500, 240)
window.show()
app.exec()
