"""Rows shared by the catalog and inventory views."""

from dataclasses import dataclass

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

from edit_changes import ItemChange
from item_catalog import ItemKey


@dataclass(frozen=True, slots=True)
class ItemRow:
    item_id: ItemKey
    name: str
    category: str
    quantity: int | None
    change: ItemChange | None

    def text(self,column):
        if column==0:return self.name
        if column==1:return '—' if isinstance(self.item_id,str) else str(self.item_id)
        if column==2:return self.category
        return '—' if self.quantity is None else str(self.quantity)


class InventoryModel(QAbstractTableModel):
    def __init__(self, icon, translate, parent=None):
        super().__init__(parent)
        self.rows = []
        self.positions = {}
        self.headers = ('', '', '', '')
        self.icon = icon
        self.translate = translate

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.headers)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if (orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole
                and 0 <= section < len(self.headers)):
            return self.headers[section]
        return super().headerData(section, orientation, role)

    def set_headers(self, headers):
        self.headers = headers
        self.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, len(headers) - 1)
        if self.rows:
            self.dataChanged.emit(self.index(0, 0), self.index(len(self.rows) - 1, 3),
                                  [Qt.ItemDataRole.ToolTipRole])

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self.rows[index.row()]
        column = index.column()
        if role == Qt.ItemDataRole.UserRole:
            return row.item_id
        if role == Qt.ItemDataRole.UserRole + 1:
            return row.change
        if role == Qt.ItemDataRole.DecorationRole and column == 0:
            return self.icon(row.item_id)
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return Qt.AlignmentFlag.AlignCenter if column else Qt.AlignmentFlag.AlignVCenter
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole):
            if role == Qt.ItemDataRole.ToolTipRole and row.change and column in (0, 3):
                change = row.change
                label = self.translate('Изменено', 'Changed')
                return f'{row.name}\n{label}: {change.before} → {change.after}'
            return row.text(column)
        return None

    def index_for_id(self, item_id):
        return self.index(self.positions.get(item_id, -1), 0)

    def replace_rows(self, rows):
        positions = {row.item_id: i for i, row in enumerate(rows)}
        if positions != self.positions:
            self.beginResetModel()
            self.rows = rows
            self.positions = positions
            self.endResetModel()
            return True
        changed = [i for i, (old, new) in enumerate(zip(self.rows, rows)) if old != new]
        self.rows = rows
        if changed:
            self.dataChanged.emit(self.index(changed[0], 0), self.index(changed[-1], 3))
        return False

    def refresh_icons(self):
        if self.rows:
            self.dataChanged.emit(self.index(0, 0), self.index(len(self.rows) - 1, 0),
                                  [Qt.ItemDataRole.DecorationRole])
