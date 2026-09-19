"""Native OLIVE desktop entry point with selectable Qt presentation."""

import sys
import time
import logging
import os

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QLockFile

from ..config import DATA_DIR
from .feature_registry import default_registry
from .runtime import BackendBridge
from .themes import apply_theme
from .window_manager import WindowManager
from .notifications import NotificationCenter


class OliveApplication:
    def __init__(self, argv=None, factory=None, presentation=None):
        started = time.perf_counter()
        self.qt = QApplication.instance() or QApplication(argv or sys.argv)
        self.qt.setApplicationName("OLIVE")
        self.qt.setOrganizationName("OLIVE")
        self.qt.setQuitOnLastWindowClosed(False)
        self.lock = QLockFile(str(DATA_DIR / "qt-runtime.lock"))
        if not self.lock.tryLock(0):
            raise RuntimeError("A Qt OLIVE runtime is already using this data directory")
        from ..runtime.profile_lock import ProfileLock
        try:
            self.profile_lock = ProfileLock(DATA_DIR).acquire()
        except Exception:
            self.lock.unlock()
            raise
        apply_theme(self.qt)
        self.bridge = BackendBridge(factory)
        self.manager = WindowManager(self.bridge, default_registry(), DATA_DIR / "ui-qt-state.json",
                                     presentation=presentation or os.environ.get("OLIVE_PRESENTATION", "midnight"))
        if self.manager.experience:
            from .experience.resources import application_icon
            self.qt.setWindowIcon(application_icon())
        self.notifications = NotificationCenter(self.manager)
        self.bridge.event.connect(self.on_event)
        self.bridge.ready.connect(lambda: self.bridge.call("data.settings", self.initial_settings))
        self.manager.open("home")
        self.manager.create_tray()
        self.bridge.start()
        self.startup_ms = round((time.perf_counter() - started) * 1000, 1)
        logging.getLogger(__name__).info("Qt Home constructed in %.1f ms", self.startup_ms)

    def initial_settings(self, value, error):
        if value:
            self.manager.settings = value["settings"]
            if not self.manager.experience:
                apply_theme(self.qt, value["settings"].get("theme", "OLIVE Blue"))

    def on_event(self, topic, value):
        if topic == "settings":
            self.manager.settings = value["settings"]
            if not self.manager.experience:
                apply_theme(self.qt, value["settings"].get("theme", "OLIVE Blue"))
        elif topic == "fatal":
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.critical(None, "OLIVE", value)

    def run(self):
        result = self.qt.exec()
        self.lock.unlock()
        self.profile_lock.close()
        return result


def main():
    from ..logging_config import configure_logging

    configure_logging()
    return OliveApplication().run()


def __getattr__(name):
    if name == "DMDOApplication":
        return OliveApplication
    raise AttributeError(name)
