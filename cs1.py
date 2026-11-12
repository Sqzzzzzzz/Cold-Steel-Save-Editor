"""Inventory and item tables for Trails of Cold Steel I (XSEED PC)."""

from dataclasses import dataclass
from datetime import datetime
from os import fsync, replace
from pathlib import Path
from struct import Struct, unpack_from
from tempfile import NamedTemporaryFile
import re


SAVE_SIZE = 460992
SAVE_HEADER = bytes.fromhex("c0 08 07 00 08 00 00 00")
INVENTORY_OFFSET = 0x40C24
SLOTS = 4096
RECORD = Struct("<HH32s")
INVENTORY_END = INVENTORY_OFFSET + SLOTS * RECORD.size
EMPTY_ID = 9999
EMPTY_RECORD = RECORD.pack(EMPTY_ID, 0, bytes(32))
ORBMENTS_OFFSET = 0x11C0
ORBMENT_SLOTS = 16
ORBMENT_SIZE = 18

CATEGORIES = {
    "all": ("Инвентарь", "Inventory"),
    "equipment": ("Снаряжение", "Equipment"),
    "quartz": ("Кварц", "Quartz"),
    "master": ("Мастер-кварц", "Master Quartz"),
    "materials": ("Материалы", "Materials"),
    "books": ("Книги", "Books"),
    "key": ("Ключевые", "Key items"),
    "dlc": ("DLC-предметы", "DLC items"),
    "items": ("Расходники", "Consumables"),
}


@dataclass(frozen=True)
class CatalogItem:
    name: str
    description: str
    category: str
    limit: int
    icon_type: int
    element: int
    editable: bool = True


def item_category(item_id: int, icon_type: int) -> str:
    if 2400 <= item_id <= 2455 or 2600 <= item_id <= 2604 or 2700 <= item_id <= 2716:
        return "dlc"
    if item_id in (50, 51, 52) or icon_type in (0x80, 0xB4):
        return "materials"
    if icon_type in (0x83, 0xC3):
        return "books"
    if icon_type == 0xAA:
        return "quartz"
    if icon_type == 0xAB:
        return "master"
    if 0x8C <= icon_type <= 0xA4 or icon_type == 0xC4:
        return "equipment"
    if icon_type in (0x82, 0xC9) and item_id != 25:
        return "key"
    return "items"


def read_catalog(path: Path) -> dict[int, CatalogItem]:
    """Read the Sen I item layout documented by SenPatcher's native/sen1/tbl.cpp."""
    with path.open("rb") as stream:
        data = stream.read(2 * 1024 * 1024 + 1)
    if not 2 <= len(data) <= 2 * 1024 * 1024:
        raise ValueError("Invalid t_item.tbl size.")
    count = unpack_from("<H", data)[0]
    result = {}
    pos = 2
    for _ in range(count):
        if data[pos:pos + 5] != b"item\0" or pos + 11 > len(data):
            raise ValueError("Expected a Cold Steel I t_item.tbl.")
        start = pos + 7
        item_id = unpack_from("<H", data, start)[0]
        flags_end = data.index(0, start + 4)
        metadata = flags_end + 1
        name_start = metadata + 46
        name_end = data.index(0, name_start)
        desc_end = data.index(0, name_end + 1)
        # Some original tables have stale length fields. The strings delimit item records.
        pos = desc_end + 1
        name = data[name_start:name_end].decode("utf-8").strip()
        description = data[name_end + 1:desc_end].decode("utf-8").strip()
        description = re.sub(r"#\d+[A-Z]", "", description)
        if item_id in result:
            raise ValueError(f"Duplicate item ID {item_id:04X} in t_item.tbl.")
        icon_type, element = data[metadata:metadata + 2]
        limit = data[metadata + 39]
        editable = (
            bool(name) and not name.startswith("◆") and "(Dev Use)" not in name
            and icon_type != 0x80 and not 250 <= item_id <= 258
            and item_id != EMPTY_ID and 1 <= limit <= 99
        )
        result[item_id] = CatalogItem(
            name, description, item_category(item_id, icon_type), limit, icon_type, element, editable
        )
    if pos != len(data) or not any(item.editable for item in result.values()):
        raise ValueError("Invalid Cold Steel I item table.")
    return result


class Save:
    def __init__(self, data: bytes):
        if len(data) != SAVE_SIZE or not data.startswith(SAVE_HEADER):
            raise ValueError("Expected a Cold Steel I XSEED PC save (460,992 bytes, version 8).")

        items = {}
        empty_started = False
        for item_id, quantity, extra in RECORD.iter_unpack(data[INVENTORY_OFFSET:INVENTORY_END]):
            if item_id == EMPTY_ID and quantity == 0 and not any(extra):
                empty_started = True
                continue
            if empty_started or item_id == EMPTY_ID or not 1 <= quantity <= 99 or any(extra):
                raise ValueError("Unrecognized inventory record in the save.")
            if item_id in items:
                raise ValueError(f"Duplicate inventory ID {item_id:04X} in the save.")
            items[item_id] = quantity

        self.original = data
        self.original_items = items
        self.items = items.copy()
        self.equipped_masters = {
            unpack_from("<H", data, ORBMENTS_OFFSET + slot * ORBMENT_SIZE)[0]
            for slot in range(ORBMENT_SLOTS)
        } - {EMPTY_ID}

    @classmethod
    def open(cls, path: Path) -> "Save":
        before = path.stat()
        with path.open("rb") as stream:
            data = stream.read(SAVE_SIZE + 1)
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError("The save changed while it was being read. Reopen it.")
        return cls(data)

    @property
    def changed(self) -> bool:
        return self.items != self.original_items

    def set_quantity(self, item_id: int, quantity: int, item: CatalogItem) -> None:
        if type(item_id) is not int or not 0 <= item_id < 65536 or item_id == EMPTY_ID or not item.editable:
            raise ValueError("This item cannot be edited.")
        if type(quantity) is not int or not 0 <= quantity <= min(item.limit, 99):
            raise ValueError(f"Quantity must be between 0 and {item.limit}.")
        if quantity and item.category == "master" and item_id in self.equipped_masters:
            raise ValueError("This Master Quartz is already equipped.")
        if quantity == 0:
            self.items.pop(item_id, None)
        else:
            if item_id not in self.items and len(self.items) >= SLOTS:
                raise ValueError("The inventory has no free slots.")
            self.items[item_id] = quantity

    def edited_bytes(self) -> bytes:
        if not self.changed:
            return self.original
        # Keep the original order when an item is removed and added back.
        records = b"".join(
            RECORD.pack(item_id, self.items[item_id], bytes(32))
            for item_id in dict.fromkeys((*self.original_items, *self.items))
            if item_id in self.items
        )
        empty = EMPTY_RECORD * (SLOTS - len(self.items))
        return self.original[:INVENTORY_OFFSET] + records + empty + self.original[INVENTORY_END:]

    def write(self, path: Path, *, original_path: bool) -> Path | None:
        """Replace a file atomically after copying its previous bytes to a unique backup."""
        try:
            existing = Save.open(path).original
        except FileNotFoundError:
            existing = None
        if original_path and existing != self.original:
            raise ValueError("The source save changed on disk. Reopen it or save a copy.")
        candidate = self.edited_bytes()
        Save(candidate)
        if candidate == existing:
            return None

        backup = None
        temporary = None
        try:
            with NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(candidate)
                stream.flush()
                fsync(stream.fileno())
            if existing is not None:
                stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
                backup = path.with_name(f"{path.name}.{stamp}.bak")
                with backup.open("xb") as stream:
                    stream.write(existing)
                    stream.flush()
                    fsync(stream.fileno())
            try:
                latest = Save.open(path).original
            except FileNotFoundError:
                latest = None
            if latest != existing:
                raise ValueError("The destination changed on disk during the write.")
            replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return backup
