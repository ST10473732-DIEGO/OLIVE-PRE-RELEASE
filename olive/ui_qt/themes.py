from dataclasses import dataclass
from PySide6.QtGui import QPalette, QColor
from ..themes import THEMES, get_theme


@dataclass(frozen=True)
class Tokens:
    spacing: int = 12
    padding: int = 24
    radius: int = 8
    control_height: int = 34
    body: int = 13
    heading: int = 26


TOKENS = Tokens()
THEME_NAMES = [*THEMES, "Light"]


def apply_theme(application, name="OLIVE Blue"):
    colors = get_theme(name)
    if name == "Light":
        colors.update(
            bg="#f3f5f8",
            surface="#ffffff",
            surface2="#e9eef5",
            border="#ccd5e0",
            text="#172434",
            text_secondary="#526378",
            accent="#1764b5",
        )
    c = colors
    application.setStyle("Fusion")
    palette = QPalette()
    for role, key in [
        (QPalette.ColorRole.Window, "bg"),
        (QPalette.ColorRole.WindowText, "text"),
        (QPalette.ColorRole.Base, "surface"),
        (QPalette.ColorRole.AlternateBase, "surface2"),
        (QPalette.ColorRole.Text, "text"),
        (QPalette.ColorRole.Button, "surface2"),
        (QPalette.ColorRole.ButtonText, "text"),
        (QPalette.ColorRole.Highlight, "accent"),
        (QPalette.ColorRole.PlaceholderText, "text_secondary"),
    ]:
        palette.setColor(role, QColor(c[key]))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("white"))
    application.setPalette(palette)
    application.setStyleSheet(f"""
        QWidget {{ color: {c["text"]}; font-family: "Segoe UI"; font-size: 13px; }}
        QMainWindow, QDialog, QWidget#page {{ background: {c["bg"]}; }}
        QLabel#title {{ font-size: 28px; font-weight: 600; }}
        QLabel#subtitle {{ color: {c["text_secondary"]}; font-size: 14px; }}
        QFrame#card {{ background: {c["surface"]}; border: 1px solid {c["border"]}; border-radius: 12px; }}
        QPushButton, QToolButton {{ background: {c["surface2"]}; border: 1px solid {c["border"]};
            border-radius: 6px; padding: 8px 12px; min-height: 18px; }}
        QPushButton:hover, QToolButton:hover {{ border-color: {c["accent"]}; }}
        QPushButton:focus, QLineEdit:focus, QPlainTextEdit:focus {{ border: 1px solid {c["accent"]}; }}
        QPushButton#primary {{ background: {c["accent"]}; color: white; border: none; }}
        QPushButton:disabled {{ color: {c["text_secondary"]}; }}
        QLineEdit, QPlainTextEdit, QTextEdit, QTextBrowser, QSpinBox, QDoubleSpinBox, QComboBox {{
            background: {c["surface"]}; border: 1px solid {c["border"]}; border-radius: 5px; padding: 6px; }}
        QTreeView, QListView, QTableView {{ background: {c["surface"]}; alternate-background-color: {c["surface2"]};
            border: 1px solid {c["border"]}; selection-background-color: {c["surface2"]}; }}
        QHeaderView::section, QTabBar::tab {{ background: {c["surface2"]}; padding: 9px; border: none; }}
        QTabBar::tab:selected {{ border-bottom: 2px solid {c["accent"]}; }}
        QMenuBar, QMenu, QToolBar, QStatusBar {{ background: {c["surface"]}; }}
        QMenu::item:selected {{ background: {c["surface2"]}; }}
        QDockWidget::title {{ background: {c["surface2"]}; padding: 8px; }}
        QSplitter::handle {{ background: {c["border"]}; }}
        QScrollArea {{ border: none; }}
        QToolTip {{ background: {c["surface2"]}; color: {c["text"]}; border: 1px solid {c["border"]}; }}
    """)
    return colors
