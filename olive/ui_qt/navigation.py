"""Workspace history and optional context; navigation never restarts services."""

from PySide6.QtCore import QObject, Signal


class NavigationController(QObject):
    changed = Signal(str)
    context_changed = Signal(object)

    def __init__(self, registry, activate, parent=None):
        super().__init__(parent)
        self.registry, self.activate = registry, activate
        self.history = []
        self.position = -1
        self.project_id = None

    @property
    def current(self):
        return self.history[self.position] if self.position >= 0 else None

    def open(self, feature_id):
        self.registry.get(feature_id)
        page = self.activate(feature_id)
        if feature_id != self.current:
            self.history = self.history[:self.position + 1] + [feature_id]
            self.history = self.history[-100:]
            self.position = len(self.history) - 1
        self.changed.emit(feature_id)
        return page

    def back(self):
        if self.position > 0:
            self._move(self.position - 1)

    def forward(self):
        if self.position + 1 < len(self.history):
            self._move(self.position + 1)

    def _move(self, position):
        self.activate(self.history[position])
        self.position = position
        self.changed.emit(self.current)

    def set_project(self, project_id):
        if project_id is not None and (not isinstance(project_id, str) or len(project_id) > 200):
            raise ValueError("Invalid project context")
        if project_id != self.project_id:
            self.project_id = project_id
            self.context_changed.emit(project_id)
