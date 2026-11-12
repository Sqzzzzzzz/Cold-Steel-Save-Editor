"""Read the original XSEED PC Cold Steel I item table without touching save files."""

from dataclasses import dataclass
from pathlib import Path
import re
from struct import unpack_from


EMPTY_ID = 9999


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
