"""One primary window with cached feature workspaces and persistent navigation."""

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QStackedWidget, QListWidget, QListWidgetItem, QToolBar, QLabel
from ..icons import icon


class MainWindow(QMainWindow):
    feature_id = "main"

    def __init__(self, manager):
        super().__init__()
        self.manager = manager
        self.bridge = manager.bridge
        self.setWindowTitle("OLIVE")
        self.setWindowIcon(icon("SP_ComputerIcon"))
        self.resize(1380, 900)
        self.setMinimumSize(960, 640)
        self.collapsed = bool(manager.state.get("main").get("rail_collapsed", False))
        host = QWidget()
        layout = QHBoxLayout(host)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.rail = QListWidget()
        self.rail.setObjectName("workspaceNavigation")
        self.rail.setAccessibleName("OLIVE workspaces")
        self.rail.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.items = {}
        for feature in manager.registry.list():
            item = QListWidgetItem(icon(feature.icon), feature.title)
            item.setData(Qt.ItemDataRole.UserRole, feature.id)
            item.setToolTip(feature.title)
            item.setSizeHint(QSize(160, 38))
            item.setData(Qt.ItemDataRole.AccessibleTextRole, feature.title)
            self.rail.addItem(item)
            self.items[feature.id] = item
        self.rail.currentItemChanged.connect(lambda item, previous: manager.open(item.data(Qt.ItemDataRole.UserRole)) if item else None)
        layout.addWidget(self.rail)
        self.stack = QStackedWidget()
        self.stack.setObjectName("workspaceStack")
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(host)
        bar = QToolBar("OLIVE navigation", self)
        bar.setObjectName("mainNavigationToolbar")
        bar.setMovable(False)
        self.addToolBar(bar)
        bar.addAction("Navigation", self.toggle_rail)
        self.back_action = bar.addAction("Back", manager.navigation.back)
        self.back_action.setShortcut(QKeySequence("Alt+Left"))
        self.forward_action = bar.addAction("Forward", manager.navigation.forward)
        self.forward_action.setShortcut(QKeySequence("Alt+Right"))
        bar.addAction("Home", lambda: manager.open("home"))
        self.heading = QLabel("OLIVE")
        bar.addWidget(self.heading)
        self.popout_action = bar.addAction("Pop out", lambda: manager.popout(manager.navigation.current))
        self.stop_action = bar.addAction("STOP CONTROL", self.bridge.stop_control)
        self.stop_action.setVisible(False)
        menu = self.menuBar().addMenu("OLIVE")
        for feature in manager.registry.list():
            action = menu.addAction(feature.title, lambda checked=False, fid=feature.id: manager.open(fid))
            if feature.id in ("home", "chat", "agent", "studio", "research"):
                action.setShortcut(QKeySequence("Ctrl+" + str(("home", "chat", "agent", "studio", "research").index(feature.id) + 1)))
        palette = menu.addAction("Command palette", manager.command_palette)
        palette.setShortcuts([QKeySequence("Ctrl+K"), QKeySequence("Ctrl+Shift+P")])
        menu.addAction("Exit OLIVE", manager.exit)
        manager.navigation.changed.connect(self.navigated)
        self.bridge.event.connect(self.on_event)
        self.apply_rail()

    def navigated(self, feature_id):
        self.rail.blockSignals(True)
        self.rail.setCurrentItem(self.items[feature_id])
        self.rail.blockSignals(False)
        title = self.manager.registry.get(feature_id).title
        self.heading.setText("  OLIVE · " + title + "  ")
        self.setWindowTitle("OLIVE — " + title)
        self.back_action.setEnabled(self.manager.navigation.position > 0)
        self.forward_action.setEnabled(self.manager.navigation.position + 1 < len(self.manager.navigation.history))
        self.popout_action.setEnabled(feature_id in self.manager.POPOUT_FEATURES)

    def toggle_rail(self):
        self.collapsed = not self.collapsed
        self.apply_rail()

    def apply_rail(self):
        self.rail.setFixedWidth(52 if self.collapsed else 190)
        for key, item in self.items.items():
            item.setText("" if self.collapsed else self.manager.registry.get(key).title)

    def layout_state(self):
        return {"rail_collapsed": self.collapsed}

    def on_event(self, topic, value):
        if topic == "notification":
            self.statusBar().showMessage(value.get("message", ""), 12000)
        elif topic == "status":
            self.statusBar().showMessage(str(value.get("ollama", "Local-first")) + " · Agent " + str(value.get("agent", "idle")))
        elif topic == "desktop":
            self.stop_action.setVisible(bool(value.get("settings", {}).get("enabled") or value.get("active")))

    def closeEvent(self, event):
        if self.manager.exiting:
            event.accept()
        else:
            event.ignore()
            self.manager.exit()


class WorkspacePopout(QMainWindow):
    def __init__(self, manager, page):
        super().__init__()
        self.manager, self.page = manager, page
        self.setWindowTitle(page.windowTitle())
        self.setWindowIcon(page.windowIcon())
        self.resize(1120, 800)
        self.setCentralWidget(page)
        bar = QToolBar("Workspace", self)
        bar.setObjectName("popoutToolbar")
        self.addToolBar(bar)
        bar.addAction("Return to OLIVE", lambda: manager.reattach(page.feature_id))
        palette = bar.addAction("Commands", manager.command_palette)
        palette.setShortcuts([QKeySequence("Ctrl+K"), QKeySequence("Ctrl+Shift+P")])

    def closeEvent(self, event):
        if not self.manager.exiting:
            self.manager.reattach(self.page.feature_id)
        event.accept()
