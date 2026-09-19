from pathlib import Path
import sys
from PySide6.QtGui import QIcon


def asset_root():
    return (Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[3])) / "assets").resolve()


def application_icon():
    return QIcon(str(asset_root() / "branding" / "olive.ico"))
