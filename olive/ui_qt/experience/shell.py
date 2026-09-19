"""One primary window: QML navigation and cached QWidget workspaces."""
from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QStackedWidget, QDockWidget, QLabel, QPushButton, QCheckBox)
from ..windows.base import FeatureWindow
from .surface import QuickSurface
from .resources import application_icon


class HomeExperience(FeatureWindow):
    def __init__(self, manager):
        super().__init__(manager, "home")
        self.surface = QuickSurface(manager.experience, "Experience.qml", self)
        self.setCentralWidget(self.surface)
        self.statusBar().hide()

    def refresh(self):
        if self.bridge.is_ready:
            self.manager.experience.refresh()


class MidnightShell(QMainWindow):
    feature_id = "main"

    def __init__(self, manager):
        super().__init__()
        self.manager = manager
        self.controller = c = manager.experience
        self.setWindowTitle("OLIVE")
        self.setWindowIcon(application_icon())
        self.resize(1380, 900)
        self.setMinimumSize(800, 600)
        host = QWidget(self)
        layout = QVBoxLayout(host); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(0)
        self.header = QuickSurface(c, "Header.qml", host); self.header.setFixedHeight(64)
        layout.addWidget(self.header)
        row = QHBoxLayout(); row.setSpacing(0)
        self.rail = QuickSurface(c, "Rail.qml", host)
        row.addWidget(self.rail)
        self.stack = QStackedWidget(host); self.stack.setObjectName("workspaceStack")
        row.addWidget(self.stack, 1); layout.addLayout(row, 1)
        self.setCentralWidget(host)
        self.drawer = QDockWidget("Activity", self); self.drawer.setObjectName("experienceDrawer")
        self.drawer.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetClosable)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.drawer)
        self.drawer.hide()
        self.drawer_kind = ""
        c.drawerRequested.connect(self.show_drawer)
        c.changed.connect(self.update_state)
        for title, shortcut, callback in [
            ("Commands", "Ctrl+K", manager.command_palette),
            ("Commands", "Ctrl+Shift+P", manager.command_palette),
            ("Back", "Alt+Left", manager.navigation.back),
            ("Forward", "Alt+Right", manager.navigation.forward),
            *[(name.title(), f"Ctrl+{i+1}", lambda name=name: c.navigate(name))
              for i, name in enumerate(("home", "chat", "agent", "studio", "research"))],
        ]:
            action = QAction(title, self); action.setShortcut(QKeySequence(shortcut))
            action.triggered.connect(callback); self.addAction(action)
        self.update_state()

    def update_state(self):
        c = self.controller
        self.header.setVisible(not c.welcome)
        self.rail.setVisible(not c.welcome and c.page != "home")
        self.rail.setFixedWidth(240 if c.expanded else 72)
        self.setWindowTitle("OLIVE" if c.welcome else "OLIVE — " + c.pageTitle)
        if self.drawer_kind == "activity" and self.drawer.isVisible():
            self.activity_text.setText("\n\n".join(
                [f'{item["title"]} · {item["state"].replace("_", " ").lower()}' for item in c.activities]
                + (["A decision needs your approval."] if c._approvals else [])
            ) or "No tasks are running.")

    def show_drawer(self, kind):
        self.drawer_kind = kind
        old = self.drawer.widget()
        page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(24, 24, 24, 24)
        page.setMinimumWidth(300)
        if kind == "appearance":
            self.drawer.setWindowTitle("Appearance")
            for text, checked, callback in [
                ("Light theme", self.controller.lightTheme, self.controller.setLightTheme),
                ("Reduced motion", self.controller.reducedMotion, self.controller.setReducedMotion),
                ("Show Welcome on startup", self.controller._welcome_pref, self.controller.setShowWelcome),
            ]:
                check = QCheckBox(text); check.setChecked(checked); check.toggled.connect(callback); layout.addWidget(check)
            button = QPushButton("Component gallery"); button.clicked.connect(self.controller.showGallery); layout.addWidget(button)
        elif kind == "context":
            self.drawer.setWindowTitle("Selected context")
            label = QLabel(self.controller.contextLabel or "No workspace or file is selected.")
            label.setTextFormat(Qt.TextFormat.PlainText); label.setWordWrap(True); layout.addWidget(label)
            label = QLabel("Clear removes the current workspace and file selection. Pending actions keep their own destinations and attachments.")
            label.setWordWrap(True); layout.addWidget(label)
            clear = QPushButton("Clear selection"); clear.setEnabled(not self.controller.busy)
            clear.clicked.connect(self.controller.clearContext); clear.clicked.connect(self.drawer.hide); layout.addWidget(clear)
        else:
            self.drawer.setWindowTitle("Activity")
            self.activity_text = QLabel(); self.activity_text.setWordWrap(True); layout.addWidget(self.activity_text)
            review = QPushButton("Review pending approval")
            review.clicked.connect(self.review_approval); layout.addWidget(review)
        layout.addStretch()
        self.drawer.setWidget(page)
        if old is not None: old.deleteLater()
        self.drawer.show(); self.update_state()

    def review_approval(self):
        for dialog in self.manager.dialogs.values():
            dialog.show(); dialog.raise_(); dialog.activateWindow(); break

    def event(self, event):
        result = super().event(event)
        if hasattr(self, "controller") and event.type() in {QEvent.Type.WindowStateChange, QEvent.Type.Show, QEvent.Type.Hide}:
            self.controller.set_window_active(self.isVisible() and not self.isMinimized())
        return result

    def closeEvent(self, event):
        if self.manager.exiting: event.accept()
        else:
            event.ignore(); self.manager.exit()
