"""Shared, bounded, non-modal desktop notifications."""

from collections import deque
from PySide6.QtCore import QObject, Signal, Slot


class NotificationCenter(QObject):
    posted = Signal(str, str)
    KINDS = {"success", "info", "warning", "error"}

    def __init__(self, manager):
        super().__init__(manager)
        self.manager = manager
        self.history = deque(maxlen=100)
        manager.bridge.event.connect(self.receive)

    @Slot(str, object)
    def receive(self, topic, value):
        if topic == "notification":
            self.show(value.get("message", ""), value.get("kind", "info"))
        elif topic == "memory_suggestion":
            self.show("A memory suggestion is ready. Open Memory → Suggestions to review it.", "info")

    def show(self, message, kind="info"):
        kind = kind if kind in self.KINDS else "info"
        self.history.append({"message": message, "kind": kind})
        for window in self.manager.windows.values():
            window.statusBar().showMessage(f"{kind.title()}: {message}", 12000)
        self.posted.emit(message, kind)
