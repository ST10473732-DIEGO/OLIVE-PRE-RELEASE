"""Small bounded presentation models. No repositories or tools are exposed."""
from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt


class RowsModel(QAbstractListModel):
    ROLES = ("key", "title", "subtitle", "feature", "glyph", "pinned", "kind")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = []

    def roleNames(self):
        return {Qt.UserRole + i + 1: name.encode() for i,name in enumerate(self.ROLES)}

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def data(self,index,role=Qt.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.rows):
            return None
        name = self.roleNames().get(role)
        return self.rows[index.row()].get(name.decode(), "") if name else None

    def replace(self, rows):
        self.beginResetModel()
        self.rows = list(rows)[:100]
        self.endResetModel()
