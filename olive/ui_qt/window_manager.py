import base64
import uuid
import logging

from PySide6.QtCore import QByteArray, QObject, Slot, QTimer, Qt
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon, QStyle

from .commands import CommandPalette
from .dialogs.confirmation import ConfirmationDialog
from .window_state import WindowStateStore

log = logging.getLogger(__name__)


class WindowManager(QObject):
    POPOUT_FEATURES = {"chat", "studio", "research", "desktop"}

    def __init__(self, bridge, registry, state_path, presentation="legacy"):
        super().__init__()
        self.bridge, self.registry = bridge, registry
        self.state = WindowStateStore(state_path)
        self.windows = {}
        # Compatibility name for the cached workspace instances, not top-level windows.
        self.pages = self.windows
        self.main = None
        self.popouts = {}
        from .navigation import NavigationController
        self.navigation = NavigationController(registry, self.activate_workspace, self)
        self.dialogs = {}
        self.exiting = False
        self.settings = {}
        self.tray = None
        bridge.confirmation.connect(self.confirm)
        bridge.stopped.connect(self.finish_exit)
        from .desktop_hotkey import DesktopStopHotkey
        self.desktop_hotkey = DesktopStopHotkey(lambda: self.bridge.stop_control())
        self.desktop_hotkey_installed = False
        bridge.event.connect(self.desktop_status)
        self.presentation = presentation
        self.experience = None
        if presentation == "midnight":
            from .experience.controller import ExperienceController
            self.experience = ExperienceController(self)
            self.experience.tokens.apply_widgets(QApplication.instance())

    def desktop_status(self, topic, value):
        if topic == "interaction_navigation":
            if value.get("feature") in {"projects", "studio", "research", "agent"}:
                self.open(value["feature"])
            return
        if topic == "desktop":
            settings = value.get("settings", {})
            enabled = settings.get("enabled", False) and bool(settings.get("emergency_shortcut"))
            self.desktop_hotkey.configure(enabled)
            if self.desktop_hotkey.registered and not self.desktop_hotkey_installed:
                QApplication.instance().installNativeEventFilter(self.desktop_hotkey)
                self.desktop_hotkey_installed = True
            elif not self.desktop_hotkey.registered and self.desktop_hotkey_installed:
                QApplication.instance().removeNativeEventFilter(self.desktop_hotkey)
                self.desktop_hotkey_installed = False

    def open(self, feature_id):
        return self.navigation.open(feature_id)

    def ensure_main(self):
        if self.main is None:
            if self.experience:
                from .experience.shell import MidnightShell as MainWindow
            else:
                from .windows.shell import MainWindow
            self.main = MainWindow(self)
            self.restore_window(self.main)
        return self.main

    def activate_workspace(self, feature_id):
        shell = self.ensure_main()
        if feature_id in self.popouts:
            self.reattach(feature_id, navigate=False)
        window = self.workspace(feature_id)
        if shell.stack.indexOf(window) < 0:
            window.setParent(shell.stack, Qt.WindowType.Widget)
            window.setMinimumSize(0, 0)
            shell.stack.addWidget(window)
        shell.stack.setCurrentWidget(window)
        window.show()
        shell.showNormal() if shell.isMinimized() else shell.show()
        shell.raise_()
        shell.activateWindow()
        return window

    def workspace(self, feature_id):
        feature = self.registry.get(feature_id)
        key = feature_id
        if key not in self.windows:
            if feature.factory is not None:
                window = feature.factory(self)
            elif feature_id == "home":
                if self.experience:
                    from .experience.shell import HomeExperience as HomeWindow
                else:
                    from .windows.home import HomeWindow

                window = HomeWindow(self)
            elif feature_id == "chat":
                if self.experience:
                    from .experience.chat import ChatExperience as ChatWindow
                else:
                    from .windows.chat import ChatWindow

                window = ChatWindow(self)
            elif feature_id == "agent":
                from .windows.agent import AgentWindow

                window = AgentWindow(self)
            elif feature_id == "research":
                from .windows.research import ResearchWindow

                window = ResearchWindow(self)
            elif feature_id == "desktop":
                from .windows.desktop import DesktopWindow

                window = DesktopWindow(self)
            elif feature_id == "studio":
                if self.experience:
                    from .experience.studio import StudioExperience as StudioWindow
                else:
                    from .studio.window import StudioWindow

                window = StudioWindow(self)
            elif feature_id in {"settings", "diagnostics"}:
                from .windows.settings import SettingsWindow, DiagnosticsWindow

                window = SettingsWindow(self) if feature_id == "settings" else DiagnosticsWindow(self)
            else:
                from .windows.data import DataWindow

                window = DataWindow(self, feature_id)
            self.windows[key] = window
            self.restore_window(window, geometry=False)
            if hasattr(window, "refresh"):
                window.refresh()
        window = self.windows[key]
        return window

    def popout(self, feature_id):
        if feature_id not in self.POPOUT_FEATURES:
            raise ValueError("This workspace stays in the main window")
        if feature_id in self.popouts:
            self.popouts[feature_id].raise_()
            self.popouts[feature_id].activateWindow()
            return self.popouts[feature_id]
        from .windows.shell import WorkspacePopout
        page = self.workspace(feature_id)
        shell = self.ensure_main()
        shell.stack.removeWidget(page)
        window = WorkspacePopout(self, page)
        self.popouts[feature_id] = window
        if self.navigation.current == feature_id:
            self.open("home")
        window.show()
        return window

    def reattach(self, feature_id, navigate=True):
        window = self.popouts.pop(feature_id, None)
        if window:
            page = window.takeCentralWidget()
            page.setParent(self.ensure_main().stack, Qt.WindowType.Widget)
            self.main.stack.addWidget(page)
            window.hide()
            window.deleteLater()
        if navigate:
            self.open(feature_id)

    def restore_window(self, window, geometry=True):
        value = self.state.get(window.feature_id)
        for field, restore in (("geometry", window.restoreGeometry), ("docks", window.restoreState)):
            if field == "geometry" and not geometry:
                continue
            encoded = value.get(field)
            if isinstance(encoded, str) and len(encoded) < 100000:
                try:
                    restore(QByteArray(base64.b64decode(encoded, validate=True)))
                except (ValueError, TypeError):
                    log.warning("Invalid %s for %s; using default layout", field, window.feature_id)
        if geometry and not any(
            screen.availableGeometry().intersects(window.frameGeometry()) for screen in QApplication.screens()
        ):
            window.move(QApplication.primaryScreen().availableGeometry().topLeft())

    def save_window(self, window):
        extra = window.layout_state() if hasattr(window, "layout_state") else {}
        try:
            self.state.save(
                window.feature_id,
                {
                    **extra,
                    "geometry": base64.b64encode(bytes(window.saveGeometry())).decode("ascii"),
                    "docks": base64.b64encode(bytes(window.saveState())).decode("ascii"),
                },
            )
        except OSError:
            log.exception("Could not save optional Qt window layout")
            window.statusBar().showMessage(
                "Window layout could not be saved; application data is separate", 8000
            )

    def command_palette(self):
        palette = CommandPalette(self, QApplication.activeWindow())
        palette.exec()

    @Slot(object)
    def confirm(self, request):
        dialog = ConfirmationDialog(request, QApplication.activeWindow())
        self.dialogs[request.id] = dialog

        def done(result):
            self.bridge.answer(request.id, dialog.response)
            self.dialogs.pop(request.id, None)
            if self.experience:
                self.experience.confirmation_finished(request.id)
            dialog.deleteLater()

        dialog.finished.connect(done)
        dialog.open()

    def create_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        icon = QApplication.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        if self.experience:
            from .experience.resources import application_icon
            if not application_icon().isNull():
                icon = application_icon()
        self.tray = QSystemTrayIcon(icon, self)
        self.tray.setToolTip("OLIVE")
        menu = QMenu()
        for title, feature_id in [
            ("Open OLIVE", "home"),
            ("Open Chat", "chat"),
            ("Open Agent", "agent"),
            ("Open Studio", "studio"),
            ("Open Research", "research"),
            ("Show Active Tasks", "agent"),
        ]:
            menu.addAction(title, lambda fid=feature_id: self.open(fid))
        menu.addSeparator()
        menu.addAction("Exit", self.exit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda reason: self.open("home") if reason == QSystemTrayIcon.ActivationReason.Trigger else None
        )
        self.tray.show()
        self.tray_menu = menu

    def exit(self):
        if self.exiting:
            return
        for window in self.windows.values():
            if not window.can_close(exiting=True):
                return
        self.exiting = True
        if self.main:
            self.save_window(self.main)
            self.main.setEnabled(False)
        for window in self.windows.values():
            self.save_window(window)
            window.setEnabled(False)
            window.statusBar().showMessage("Stopping background work safely…")
        for dialog in list(self.dialogs.values()):
            dialog.reject()
        self.bridge.shutdown()

    @Slot()
    def finish_exit(self):
        self.desktop_hotkey.configure(False)
        QApplication.instance().removeNativeEventFilter(self.desktop_hotkey)
        if self.exiting:
            if self.tray:
                self.tray.hide()
            for window in self.windows.values():
                preview = getattr(window, "preview", None)
                if preview is not None:
                    preview.dispose()
            for window in self.popouts.values():
                window.hide()
            if self.main:
                self.main.hide()
            QTimer.singleShot(100, QApplication.instance().quit)
