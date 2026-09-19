import json
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QPlainTextEdit,
    QDialogButtonBox,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
)
from PySide6.QtCore import Qt


def show_details(parent, title, value):
    dialog = QDialog(parent)
    dialog.setWindowTitle("OLIVE — " + title)
    dialog.resize(760, 560)
    layout = QVBoxLayout(dialog)
    text = QPlainTextEdit()
    text.setReadOnly(True)
    text.setPlainText(
        value if isinstance(value, str) else json.dumps(value, indent=2, ensure_ascii=False, default=str)
    )
    layout.addWidget(text)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)
    dialog.exec()


def table(columns):
    widget = QTableWidget(0, len(columns))
    widget.setHorizontalHeaderLabels(columns)
    widget.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    widget.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
    widget.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    widget.horizontalHeader().setStretchLastSection(True)
    widget.setAlternatingRowColors(True)
    return widget


def populate(widget, rows, fields):
    widget.setRowCount(len(rows))
    for index, row in enumerate(rows):
        for col, field in enumerate(fields):
            value = row.get(field, "")
            item = QTableWidgetItem(str(value if value is not None else ""))
            item.setData(Qt.ItemDataRole.UserRole, row)
            widget.setItem(index, col, item)


def selected(widget):
    item = widget.item(widget.currentRow(), 0)
    return item.data(Qt.ItemDataRole.UserRole) if item else None
