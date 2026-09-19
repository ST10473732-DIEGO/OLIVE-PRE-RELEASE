"""Local QML presentation inside the existing QWidget content host."""
from pathlib import Path
import time
from PySide6.QtCore import QUrl
from PySide6.QtQuickWidgets import QQuickWidget
from PySide6.QtQuickControls2 import QQuickStyle


class QuickSurface(QQuickWidget):
    def __init__(self, controller, filename, parent=None):
        QQuickStyle.setStyle("Basic")
        super().__init__(parent)
        self.errors = []
        self.first_paint_at = None
        self.paint_count = 0
        self.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)
        self.rootContext().setContextProperty("experience", controller)
        self.rootContext().setContextProperty("tokens", controller.tokens)
        self.statusChanged.connect(self._status)
        self.setSource(QUrl.fromLocalFile(str(Path(__file__).parent / "qml" / filename)))

    def _status(self, status):
        if status == QQuickWidget.Status.Error:
            self.errors = [error.toString() for error in super().errors()]
            import logging
            logging.getLogger(__name__).error("QML presentation failed: %s", self.errors)

    def paintEvent(self, event):
        super().paintEvent(event)
        self.paint_count += 1
        if self.first_paint_at is None and self.rootObject() is not None:
            self.first_paint_at = time.perf_counter()
