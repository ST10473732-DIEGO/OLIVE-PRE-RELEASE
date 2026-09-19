"""Packaging-safe central native icon lookup."""

from PySide6.QtWidgets import QApplication, QStyle


def icon(name="SP_ComputerIcon"):
    return QApplication.style().standardIcon(
        getattr(QStyle.StandardPixmap, name, QStyle.StandardPixmap.SP_FileIcon)
    )
