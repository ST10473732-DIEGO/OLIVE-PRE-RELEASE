"""One token source for QML and retained Widgets, without network assets."""
import json
from pathlib import Path
from PySide6.QtCore import QObject, Property, Signal
from PySide6.QtGui import QColor, QFontDatabase, QPalette


class DesignTokens(QObject):
    changed = Signal()

    def __init__(self, parent=None, light=False):
        super().__init__(parent)
        self.source = json.loads(Path(__file__).with_name("tokens.json").read_text(encoding="utf-8"))
        self.light = light
        families = QFontDatabase.families()
        self.font = next((name for name in ("Segoe UI Variable", "Segoe UI") if name in families), "sans-serif")

    @Property("QVariantMap", notify=changed)
    def values(self):
        return {**self.source["light" if self.light else "dark"], **self.source["metrics"], "fontFamily": self.font}

    def set_light(self, value):
        if self.light != value:
            self.light = value
            self.changed.emit()

    def apply_widgets(self, app):
        c = self.values
        app.setStyle("Fusion")
        palette = QPalette()
        for role, key in [(QPalette.Window,"background"),(QPalette.WindowText,"text"),
            (QPalette.Base,"surface"),(QPalette.AlternateBase,"elevated"),(QPalette.Text,"text"),
            (QPalette.Button,"surface"),(QPalette.ButtonText,"text"),(QPalette.Highlight,"accent"),
            (QPalette.HighlightedText,"onAccent"),(QPalette.PlaceholderText,"muted")]:
            palette.setColor(role,QColor(c[key]))
        app.setPalette(palette)
        app.setStyleSheet(f'''
            QWidget {{ color:{c['text']}; font-family:"{self.font}"; font-size:15px; }}
            QMainWindow,QDialog,QWidget#page,QWidget#midnightChat {{ background:{c['background']}; }}
            QLabel#title {{ font-size:30px; font-weight:600; }}
            QLabel#subtitle,QLabel#quiet {{ color:{c['secondary']}; }}
            QLabel#eyebrow {{ color:{c['accent']}; font-size:12px; font-weight:600; }}
            QPushButton,QToolButton {{ background:{c['surface']}; border:1px solid {c['border']}; border-radius:10px; padding:8px 12px; min-height:22px; }}
            QPushButton:hover,QToolButton:hover {{ background:{c['elevated']}; border-color:{c['muted']}; }}
            QPushButton:pressed,QToolButton:pressed {{ background:{c['border']}; }}
            QPushButton:focus,QToolButton:focus {{ border:2px solid {c['accent']}; }}
            QPushButton#primary {{ background:{c['accent']}; color:{c['onAccent']}; border-color:{c['accent']}; font-weight:600; }}
            QPushButton#messageAction {{ border:none; background:transparent; color:{c['secondary']}; padding:2px 8px; font-size:12px; }}
            QMainWindow#studioMidnight QToolButton {{ padding:4px 7px; min-height:22px; font-size:13px; border-radius:6px; }}
            QMainWindow#studioMidnight QComboBox {{ padding:4px 8px; font-size:13px; }}
            QPushButton:disabled,QToolButton:disabled {{ color:{c['muted']}; background:{c['surface']}; }}
            QLineEdit,QPlainTextEdit,QTextEdit,QComboBox,QSpinBox,QDoubleSpinBox {{ background:{c['surface']}; border:1px solid {c['border']}; border-radius:10px; padding:8px; selection-background-color:{c['accent']}; selection-color:{c['onAccent']}; }}
            QLineEdit:focus,QPlainTextEdit:focus,QComboBox:focus {{ border-color:{c['accent']}; }}
            QTextBrowser {{ background:transparent; border:none; padding:0; }}
            QListView,QTreeView,QTableView {{ background:{c['surface']}; border:none; outline:none; selection-background-color:{c['elevated']}; selection-color:{c['text']}; }}
            QListView::item {{ padding:12px 10px; border-radius:8px; }}
            QListView::item:focus,QTreeView::item:focus {{ border:1px solid {c['accent']}; }}
            QHeaderView::section,QTabBar::tab {{ background:{c['surface']}; padding:8px 12px; border:none; }}
            QTabBar::tab:selected {{ color:{c['accent']}; border-bottom:2px solid {c['accent']}; }}
            QMenuBar,QMenu,QToolBar,QStatusBar {{ background:{c['surface']}; border:none; }}
            QMenu::item {{ padding:8px 24px; }} QMenu::item:selected {{ background:{c['elevated']}; }}
            QDockWidget::title {{ background:{c['surface']}; color:{c['secondary']}; padding:8px; font-size:13px; }}
            QSplitter::handle {{ background:{c['border']}; }} QScrollArea {{ border:none; }}
            QScrollBar:vertical {{ width:8px; background:transparent; }}
            QScrollBar::handle:vertical {{ background:{c['border']}; border-radius:4px; min-height:24px; }}
            QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical {{ height:0; }}
            QToolTip {{ color:{c['text']}; background:{c['elevated']}; border:1px solid {c['border']}; padding:6px; }}
            QWidget#studioMidnight QPushButton {{ font-size:13px; min-height:18px; padding:5px 8px; }}
            QWidget#studioMidnight QToolBar {{ spacing:4px; }}
        ''')
