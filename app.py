"""Trails of Cold Steel I inventory editor."""

import argparse
import os
from pathlib import Path
import sys

from PySide6.QtCore import QSettings, QSize, Qt
from PySide6.QtGui import QColor, QKeySequence, QLinearGradient, QPainter, QPixmap, QRegion, QShortcut
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QComboBox, QFileDialog, QFrame, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton, QSpinBox, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from cs1 import CATEGORIES, Save, read_catalog
from game_art import ASSETS, GameArt


ROOT = Path(__file__).resolve().parent
ITEM_TABLE = Path("data/text/dat_us/t_item.tbl")
SAVED_GAMES = Path.home() / "Saved Games" / "Falcom" / "ed8"
STEAM_GAME = (
    Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)"))
    / "Steam/steamapps/common/Trails of Cold Steel"
)
TITLE = "Trails of Cold Steel I"
ROLE = Qt.ItemDataRole.UserRole
ALIGN_CENTER = Qt.AlignmentFlag.AlignCenter


def label(style: str = "") -> QLabel:
    result = QLabel()
    result.setTextFormat(Qt.TextFormat.PlainText)
    result.setObjectName(style)
    return result


def inventory_table(columns: int) -> QTableWidget:
    table = QTableWidget(0, columns)
    table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.setAlternatingRowColors(True)
    table.setIconSize(QSize(22, 22))
    table.verticalHeader().hide()
    table.verticalHeader().setDefaultSectionSize(29)
    header = table.horizontalHeader()
    header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
    header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
    table.setColumnWidth(0, 87)
    if columns == 3:
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        table.setColumnWidth(2, 100)
    return table


class Banner(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("banner")
        self.setFixedHeight(120)
        self.hero = QPixmap(str(ASSETS / "hero.jpg"))

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.hero.isNull():
            return
        painter = QPainter(self)
        image = self.hero.scaled(
            self.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        painter.drawPixmap((self.width() - image.width()) // 2, (self.height() - image.height()) // 2, image)
        shade = QLinearGradient(0, 0, self.width(), 0)
        shade.setColorAt(0, QColor(11, 17, 27, 255))
        shade.setColorAt(0.42, QColor(15, 22, 32, 160))
        shade.setColorAt(0.77, QColor(15, 22, 32, 42))
        shade.setColorAt(1, QColor(11, 17, 27, 198))
        painter.fillRect(self.rect(), shade)


class Window(QMainWindow):
    def __init__(self, game: Path | None = None):
        super().__init__()
        self.settings = QSettings("ColdSteelSaveEditor", "ColdSteelI")
        self.language = int(self.settings.value("language", 0))
        self.catalog = {}
        self.save = None
        self.path = None
        self.backup = None
        self.active = "inventory"
        self.section = "all"
        self.art = GameArt()
        self.game_path = Path(game or self.settings.value("game", str(STEAM_GAME)))

        self.resize(1330, 815)
        self.setMinimumSize(1030, 640)
        self.setWindowTitle(f"{TITLE} — Inventory Editor")
        self.setWindowIcon(self.art.section_icon("equipment"))
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self.build_banner())

        body = QHBoxLayout()
        body.setContentsMargins(12, 12, 12, 12)
        body.setSpacing(12)
        outer.addLayout(body, 1)
        body.addWidget(self.build_sidebar())

        workspace = QVBoxLayout()
        workspace.setSpacing(10)
        body.addLayout(workspace, 1)
        tables = QHBoxLayout()
        tables.setSpacing(10)
        workspace.addLayout(tables, 1)
        tables.addWidget(self.build_table_panel("inventory"), 1)
        tables.addWidget(self.build_actions())
        tables.addWidget(self.build_table_panel("catalog"), 1)
        workspace.addWidget(self.build_details())
        outer.addWidget(self.build_footer())

        self.inventory.itemSelectionChanged.connect(lambda: self.select_side("inventory"))
        self.catalog_table.itemSelectionChanged.connect(lambda: self.select_side("catalog"))
        self.inventory.cellClicked.connect(lambda *_: self.select_side("inventory"))
        self.catalog_table.cellClicked.connect(lambda *_: self.select_side("catalog"))
        self.search.textChanged.connect(self.filter_catalog)
        self.filter.currentIndexChanged.connect(self.filter_catalog)
        for keys, action in (
            (QKeySequence.StandardKey.Open, self.open_dialog),
            (QKeySequence.StandardKey.Save, self.save_current),
            (QKeySequence.StandardKey.SaveAs, self.save_copy),
        ):
            QShortcut(QKeySequence(keys), self, activated=action)

        try:
            if (self.game_path / ITEM_TABLE).is_file():
                self.catalog = read_catalog(self.game_path / ITEM_TABLE)
        except (OSError, ValueError) as error:
            self.show_error(error)
        self.translate()

    def wording(self, ru: str, en: str) -> str:
        return (ru, en)[self.language]

    def build_banner(self) -> Banner:
        banner = Banner()
        layout = QHBoxLayout(banner)
        layout.setContentsMargins(23, 10, 20, 10)
        logo = label("logo")
        pixmap = QPixmap(str(ASSETS / "logo.png"))
        if pixmap.isNull():
            logo.setText(TITLE)
        else:
            visible = QRegion(pixmap.mask()).boundingRect()
            if not visible.isEmpty():
                pixmap = pixmap.copy(visible)
            logo.setPixmap(pixmap.scaled(
                294, 98, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            ))
        layout.addWidget(logo)
        layout.addStretch()
        self.game_button = QPushButton()
        self.game_button.clicked.connect(self.choose_game)
        layout.addWidget(self.game_button, alignment=Qt.AlignmentFlag.AlignTop)
        self.languages = QButtonGroup(self)
        for index, text in enumerate(("RU", "EN")):
            button = QPushButton(text)
            button.setObjectName("language")
            button.setCheckable(True)
            button.setChecked(index == self.language)
            self.languages.addButton(button, index)
            layout.addWidget(button, alignment=Qt.AlignmentFlag.AlignTop)
        self.languages.idClicked.connect(self.change_language)
        return banner

    def build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(182)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        group = QButtonGroup(self)
        self.sections = {}
        for category in CATEGORIES:
            button = QPushButton()
            button.setObjectName("nav")
            button.setCheckable(True)
            button.setIcon(self.art.section_icon(category))
            button.setIconSize(QSize(24, 24))
            button.setChecked(category == self.section)
            button.clicked.connect(lambda checked, value=category: self.change_section(value))
            group.addButton(button)
            self.sections[category] = button
            layout.addWidget(button)
        layout.addStretch()
        crest = QPixmap(str(ASSETS / "crest.png"))
        if not crest.isNull():
            emblem = label()
            emblem.setPixmap(crest.scaled(
                120, 120, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            ))
            layout.addWidget(emblem, alignment=ALIGN_CENTER)
        return sidebar

    def build_table_panel(self, side: str) -> QFrame:
        panel = QFrame()
        panel.setObjectName("panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 9, 10, 10)
        layout.setSpacing(8)
        if side == "inventory":
            self.inventory_title = label("panelTitle")
            self.inventory = inventory_table(3)
            layout.addWidget(self.inventory_title)
            layout.addWidget(self.inventory, 1)
        else:
            self.catalog_title = label("panelTitle")
            self.catalog_table = inventory_table(2)
            self.filter = QComboBox()
            self.search = QLineEdit()
            self.search.setClearButtonEnabled(True)
            controls = QHBoxLayout()
            controls.addWidget(self.filter, 1)
            controls.addWidget(self.search, 1)
            layout.addWidget(self.catalog_title)
            layout.addLayout(controls)
            layout.addWidget(self.catalog_table, 1)
        return panel

    def build_actions(self) -> QFrame:
        frame = QFrame()
        frame.setFixedWidth(116)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addStretch()
        self.add_button = QPushButton()
        self.add_button.setObjectName("add")
        self.apply_button = QPushButton()
        self.remove_button = QPushButton()
        self.add_button.clicked.connect(lambda: self.edit("add"))
        self.apply_button.clicked.connect(lambda: self.edit("set"))
        self.remove_button.clicked.connect(lambda: self.edit("remove"))
        for button in (self.add_button, self.apply_button, self.remove_button):
            layout.addWidget(button)
        layout.addSpacing(15)
        self.quantity_label = label("muted")
        self.quantity = QSpinBox()
        self.quantity.setAlignment(ALIGN_CENTER)
        self.quantity.setButtonSymbols(QSpinBox.ButtonSymbols.PlusMinus)
        self.quantity.setRange(1, 99)
        self.max_button = QPushButton()
        self.max_button.clicked.connect(lambda: self.quantity.setValue(self.quantity.maximum()))
        layout.addWidget(self.quantity_label)
        layout.addWidget(self.quantity)
        layout.addWidget(self.max_button)
        layout.addStretch()
        return frame

    def build_details(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("panel")
        panel.setFixedHeight(115)
        layout = QHBoxLayout(panel)
        layout.setContentsMargins(14, 8, 14, 8)
        self.picture = label()
        self.picture.setFixedSize(64, 64)
        self.picture.setAlignment(ALIGN_CENTER)
        layout.addWidget(self.picture)
        text = QVBoxLayout()
        self.item_name = label("itemName")
        self.item_kind = label("itemKind")
        self.item_desc = label("description")
        self.item_desc.setWordWrap(True)
        self.item_desc.setAlignment(Qt.AlignmentFlag.AlignTop)
        text.setSpacing(2)
        text.addWidget(self.item_name)
        text.addWidget(self.item_kind)
        text.addWidget(self.item_desc, 1)
        layout.addLayout(text, 1)
        self.item_meta = label("metadata")
        self.item_meta.setMinimumWidth(135)
        layout.addWidget(self.item_meta)
        return panel

    def build_footer(self) -> QFrame:
        footer = QFrame()
        footer.setObjectName("footer")
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(12, 8, 12, 8)
        self.open_button = QPushButton()
        self.open_button.clicked.connect(self.open_dialog)
        self.file_name = label("fileName")
        self.status = label("muted")
        self.copy_button = QPushButton()
        self.copy_button.clicked.connect(self.save_copy)
        self.save_button = QPushButton()
        self.save_button.setObjectName("save")
        self.save_button.clicked.connect(self.save_current)
        layout.addWidget(self.open_button)
        layout.addWidget(self.file_name)
        layout.addStretch(1)
        layout.addWidget(self.status)
        layout.addStretch(1)
        layout.addWidget(self.copy_button)
        layout.addWidget(self.save_button)
        return footer

    def translate(self):
        tr = self.wording
        self.game_button.setText(tr("Папка игры", "Game folder"))
        for key, button in self.sections.items():
            button.setText(CATEGORIES[key][self.language])
        index = max(0, self.filter.currentIndex())
        self.filter.blockSignals(True)
        self.filter.clear()
        for key, pair in CATEGORIES.items():
            self.filter.addItem(tr("Все категории", "All categories") if key == "all" else pair[self.language], key)
        self.filter.setCurrentIndex(index)
        self.filter.blockSignals(False)
        self.search.setPlaceholderText(tr("Поиск по названию или ID…", "Search by name or ID…"))
        self.inventory.setHorizontalHeaderLabels(["ID", tr("Название", "Name"), tr("Количество", "Quantity")])
        self.catalog_table.setHorizontalHeaderLabels(["ID", tr("Название", "Name")])
        self.add_button.setText(tr("Добавить", "Add"))
        self.add_button.setToolTip(tr("Добавить выбранное из каталога", "Add the selected catalog item"))
        self.apply_button.setText(tr("Изменить", "Set quantity"))
        self.apply_button.setToolTip(tr("Установить количество выбранного в инвентаре", "Set the selected inventory item's quantity"))
        self.remove_button.setText(tr("Удалить", "Remove"))
        self.remove_button.setToolTip(tr("Удалить выбранное из инвентаря", "Remove the selected inventory item"))
        self.quantity_label.setText(tr("Количество", "Quantity"))
        self.quantity.setAccessibleName(self.quantity_label.text())
        self.max_button.setText(tr("Макс.", "Max"))
        self.open_button.setText(tr("Открыть сохранение…", "Open save…"))
        self.copy_button.setText(tr("Сохранить копию…", "Save a copy…"))
        self.save_button.setText(tr("Сохранить", "Save"))
        self.refresh_table("inventory")
        self.refresh_table("catalog")

    def change_language(self, language: int):
        self.language = language
        self.settings.setValue("language", language)
        self.translate()

    def change_section(self, section: str):
        self.section = section
        self.active = "inventory"
        self.refresh_table("inventory")

    def filter_catalog(self):
        self.active = "catalog"
        self.refresh_table("catalog")

    @staticmethod
    def selected_id(table: QTableWidget) -> int | None:
        selected = table.selectedItems()
        return selected[0].data(ROLE) if selected else None

    def refresh_table(self, side: str, selected_id: int | None = None):
        inventory = side == "inventory"
        table = self.inventory if inventory else self.catalog_table
        if selected_id is None:
            selected_id = self.selected_id(table)
        category = self.section if inventory else self.filter.currentData()
        entries = (self.save.items if self.save else {}) if inventory else self.catalog
        query = "" if inventory else self.search.text().strip().casefold()
        rows = []
        for item_id in sorted(entries):
            item = self.catalog.get(item_id)
            if not inventory and (not item or not item.editable):
                continue
            if category != "all" and (item is None or item.category != category):
                continue
            name = item.name if item and item.name else self.wording("Неизвестный предмет", "Unknown item")
            hex_id = f"{item_id:04X}"
            if query and query not in name.casefold() and query.removeprefix("0x") not in hex_id.casefold():
                continue
            rows.append((item_id, hex_id, name, item))

        table.setUpdatesEnabled(False)
        table.blockSignals(True)
        table.clearContents()
        table.setRowCount(len(rows))
        target = 0
        for row, (item_id, hex_id, name, item) in enumerate(rows):
            id_cell = QTableWidgetItem(hex_id)
            id_cell.setData(ROLE, item_id)
            if item:
                id_cell.setIcon(self.art.item_icon(item_id, item))
            name_cell = QTableWidgetItem(name)
            name_cell.setData(ROLE, item_id)
            table.setItem(row, 0, id_cell)
            table.setItem(row, 1, name_cell)
            if inventory:
                count = QTableWidgetItem(str(entries[item_id]))
                count.setData(ROLE, item_id)
                count.setTextAlignment(ALIGN_CENTER)
                table.setItem(row, 2, count)
            if item_id == selected_id:
                target = row
        if rows:
            table.selectRow(target)
        table.blockSignals(False)
        table.setUpdatesEnabled(True)
        if inventory:
            self.inventory_title.setText(f"{CATEGORIES[category][self.language]} ({len(rows)})")
        else:
            self.catalog_title.setText(self.wording("Каталог предметов", "Item catalog") + f" ({len(rows)})")
        self.refresh_details()

    def select_side(self, side: str):
        self.active = side
        self.refresh_details()

    def refresh_details(self):
        tr = self.wording
        inventory_id = self.selected_id(self.inventory)
        catalog_id = self.selected_id(self.catalog_table)
        item_id = inventory_id if self.active == "inventory" else catalog_id
        if item_id is None:
            item_id = catalog_id if self.active == "inventory" else inventory_id
        item = self.catalog.get(item_id)
        catalog_item = self.catalog.get(catalog_id)
        inventory_item = self.catalog.get(inventory_id)
        owned = self.save.items if self.save else {}
        equipped = self.save.equipped_masters if self.save else set()
        can_add = bool(
            self.save and catalog_item and owned.get(catalog_id, 0) < catalog_item.limit
            and not (catalog_item.category == "master" and catalog_id in equipped)
        )
        can_edit = bool(self.save and inventory_item and inventory_item.editable)
        self.add_button.setEnabled(can_add)
        self.apply_button.setEnabled(can_edit)
        self.remove_button.setEnabled(can_edit)
        self.quantity.setEnabled(can_edit or can_add)
        self.max_button.setEnabled(can_edit or can_add)
        if item and item.editable:
            limit = item.limit
            if item_id == catalog_id and (self.active == "catalog" or inventory_id is None):
                limit = max(1, limit - owned.get(item_id, 0))
            self.quantity.setMaximum(limit)
        if item_id is None:
            self.picture.clear()
            self.item_name.setText(tr("Выберите предмет", "Select an item"))
            self.item_kind.clear()
            self.item_desc.setText(
                tr("Укажите папку игры для загрузки каталога.", "Choose the game folder to load the catalog.")
                if not self.catalog else ""
            )
            self.item_desc.setToolTip("")
            self.item_meta.clear()
        else:
            picture = self.art.item_picture(item_id, item) if item else QPixmap()
            self.picture.setPixmap(picture.scaled(
                58, 58, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            ) if not picture.isNull() else picture)
            self.item_name.setText(item.name if item and item.name else tr("Неизвестный предмет", "Unknown item"))
            self.item_kind.setText(CATEGORIES[item.category][self.language] if item else "")
            self.item_desc.setText(item.description if item else "")
            self.item_desc.setToolTip(self.item_desc.text())
            limit = tr("Макс.", "Limit") + f"  {item.limit}" if item and item.editable else tr("Только просмотр", "Read-only")
            if item and item.category == "master" and item_id in equipped:
                limit = tr("Экипирован", "Equipped")
            self.item_meta.setText(f"ID  {item_id:04X}\n{limit}")
        self.refresh_status()

    def refresh_status(self):
        tr = self.wording
        self.file_name.setText(self.path.name if self.path else tr("Сохранение не открыто", "No save open"))
        self.file_name.setToolTip(str(self.path) if self.path else "")
        self.save_button.setEnabled(bool(self.save and self.save.changed))
        self.copy_button.setEnabled(self.save is not None)
        if self.save and self.save.changed:
            self.status.setText(tr("Есть несохранённые изменения", "Unsaved changes"))
        elif self.backup:
            self.status.setText(tr("Резервная копия создана", "Backup created"))
        else:
            self.status.clear()
        self.status.setToolTip(str(self.backup) if self.backup else "")

    def edit(self, action: str):
        if self.save is None:
            return
        item_id = self.selected_id(self.catalog_table if action == "add" else self.inventory)
        item = self.catalog.get(item_id)
        if item is None:
            return
        quantity = self.quantity.value()
        if action == "add":
            quantity += self.save.items.get(item_id, 0)
        elif action == "remove":
            quantity = 0
        try:
            self.save.set_quantity(item_id, quantity, item)
        except ValueError as error:
            self.show_error(error)
            return
        self.refresh_table("inventory", item_id)

    def choose_game(self):
        start = self.game_path if self.game_path.is_dir() else Path.home()
        folder = QFileDialog.getExistingDirectory(self, self.game_button.text(), str(start))
        if not folder:
            return
        try:
            catalog = read_catalog(Path(folder) / ITEM_TABLE)
        except (OSError, ValueError) as error:
            self.show_error(error)
            return
        self.game_path = Path(folder)
        self.settings.setValue("game", folder)
        self.catalog = catalog
        self.refresh_table("inventory")
        self.refresh_table("catalog")

    def can_discard(self) -> bool:
        if not self.save or not self.save.changed:
            return True
        return QMessageBox.question(
            self, TITLE, self.wording("Отбросить несохранённые изменения?", "Discard unsaved changes?"),
            QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        ) == QMessageBox.StandardButton.Discard

    def open_dialog(self):
        start = self.path.parent if self.path else SAVED_GAMES
        if not start.is_dir():
            start = Path.home()
        filename, _ = QFileDialog.getOpenFileName(
            self, self.open_button.text(), str(start), self.wording("Сохранения (*.dat)", "Save files (*.dat)")
        )
        if filename and self.can_discard():
            self.open_save(Path(filename))

    def open_save(self, path: Path):
        try:
            save = Save.open(path)
        except (OSError, ValueError) as error:
            self.show_error(error)
            return
        self.save = save
        self.path = path.resolve()
        self.backup = None
        self.active = "inventory"
        self.refresh_table("inventory")

    def save_current(self):
        if self.save and self.save.changed:
            self.write_save(self.path)

    def save_copy(self):
        if self.save is None:
            return
        suggested = self.path.with_stem(f"{self.path.stem}-edited")
        filename, _ = QFileDialog.getSaveFileName(
            self, self.copy_button.text(), str(suggested), self.wording("Сохранения (*.dat)", "Save files (*.dat)")
        )
        if filename:
            path = Path(filename)
            self.write_save(path if path.suffix else path.with_suffix(".dat"))

    def write_save(self, path: Path):
        path = path.resolve()
        try:
            backup = self.save.write(path, original_path=path == self.path)
            saved = Save(self.save.edited_bytes())
        except (OSError, ValueError) as error:
            self.show_error(error)
            return
        self.path = path
        self.backup = backup
        self.save = saved
        self.refresh_status()
        if not backup:
            self.status.setText(self.wording("Сохранено", "Saved"))

    def show_error(self, error: Exception):
        QMessageBox.warning(self, self.wording("Операция не выполнена", "Operation failed"), str(error))

    def closeEvent(self, event):
        event.setAccepted(self.can_discard())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", type=Path, help="Cold Steel I installation directory")
    parser.add_argument("--save", type=Path, help="Open a save file at launch")
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    app.setStyle("Fusion")
    app.setStyleSheet((ROOT / "theme.qss").read_text(encoding="utf-8"))
    window = Window(args.game)
    if args.save:
        window.open_save(args.save)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
