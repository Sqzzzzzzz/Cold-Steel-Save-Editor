"""Read the original XSEED PC Cold Steel I item table without touching save files."""

from dataclasses import dataclass
from pathlib import Path
import re
from struct import unpack_from


EMPTY_ID = 9999
SEPITH_IDS = range(241, 250)
NOTEBOOK_IDS = range(250, 259)
UNOBTAINABLE_IDS = {103, 109}
ItemKey = int | str
STAT_NAMES = ("STR", "DEF", "ATS", "ADF", "ACC", "EVA", "SPD", "MOV", "HP", "EP")


@dataclass(frozen=True, slots=True)
class CatalogItem:
    name: str
    description: str
    category: str
    limit: int
    icon_type: int
    element: int
    editable: bool = True
    stats: tuple[int, ...] = ()
    listed: bool = True
    rarity: int = 0


def item_category(item_id: int, icon_type: int) -> str:
    if 2400 <= item_id <= 2455 or 2600 <= item_id <= 2604 or 2700 <= item_id <= 2716:
        return "dlc"
    if item_id in (50, 51, 52) or icon_type in (0x80, 0xB4):
        return "materials"
    if item_id in (161, 162) or item_id in NOTEBOOK_IDS or icon_type in (0x83, 0xC3):
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
        flags_end = data.find(b"\0", start + 4)
        metadata = flags_end + 1
        name_start = metadata + 46
        name_end = data.find(b"\0", name_start)
        desc_end = data.find(b"\0", name_end + 1)
        if min(flags_end, name_end, desc_end) < 0:
            raise ValueError("Invalid Cold Steel I item table.")
        # Some original tables have stale length fields. The strings delimit item records.
        pos = desc_end + 1
        try:
            name = data[name_start:name_end].decode("utf-8").strip()
            description = data[name_end + 1:desc_end].decode("utf-8").strip()
        except UnicodeDecodeError as exc:
            raise ValueError("Invalid Cold Steel I item table.") from exc
        description = re.sub(r"#\d+[A-Z]", "", description)
        if item_id in result:
            raise ValueError(f"Duplicate item ID {item_id:04X} in t_item.tbl.")
        icon_type, element = data[metadata:metadata + 2]
        stats = unpack_from("<10H", data, metadata + 15)
        limit = data[metadata + 39]
        listed = bool(name) and not name.startswith("◆") and "(Dev Use)" not in name and item_id != EMPTY_ID
        editable = (listed and icon_type != 0x80 and item_id not in NOTEBOOK_IDS
                    and item_id not in UNOBTAINABLE_IDS and 1 <= limit <= 99)
        result[item_id] = CatalogItem(
            name, description, item_category(item_id, icon_type), limit, icon_type, element, editable, stats, listed,
            rarity=data[metadata + 10] if icon_type == 0xAA else 0,
        )
    if pos != len(data) or not any(item.editable for item in result.values()):
        raise ValueError("Invalid Cold Steel I item table.")
    return result


def _reference_records(path: Path, marker: bytes, error: str):
    with path.open("rb") as stream:
        data = stream.read(128 * 1024 + 1)
    if not 2 <= len(data) <= 128 * 1024:
        raise ValueError(error)
    offsets = [match.start() for match in re.finditer(marker, data)]
    if len(offsets) != unpack_from("<H", data)[0] or not offsets or offsets[0] != 2:
        raise ValueError(error)
    # The Russian translation contains stale record lengths. The record markers delimit the rows.
    for offset, end in zip(offsets, offsets[1:] + [len(data)]):
        yield data[offset + len(marker) + 2:end]


def read_fishing_notebook(path: Path) -> dict[str, tuple[str, str]]:
    """Read QSFish names and descriptions, keeping journal keys separate from inventory IDs."""
    error = "Invalid Cold Steel I fishing notebook table."
    records = {}
    try:
        for body in _reference_records(path, b"QSFish\0", error):
            if len(body) < 100:
                raise ValueError
            fish_id = unpack_from("<H", body)[0]
            if fish_id == 24:  # The "Record" row stores the player's fishing record.
                continue
            name_end = body.index(0, 2)
            description_start = name_end + 97  # NUL after the name, then 96 bytes of fishing data.
            description_end = body.index(0, description_start)
            key = f"fish:{fish_id}"
            if name_end == 2 or key in records:
                raise ValueError
            records[key] = (
                body[2:name_end].decode("utf-8"),
                body[description_start:description_end].decode("utf-8"),
            )
    except ValueError as exc:
        raise ValueError(error) from exc
    if not records:
        raise ValueError(error)
    return records


def read_dlc_packs(path: Path) -> dict[str, tuple[str, str]]:
    """Read DLC menu entries. These IDs belong to the DLC table."""
    error = "Invalid Cold Steel I DLC table."
    records = {}
    try:
        for body in _reference_records(path, b"dlc\0", error):
            if len(body) < 2:
                raise ValueError
            pack_id = unpack_from("<H", body)[0]
            code, family, title, description, tail = body[2:].split(b"\0", 4)
            key = f"dlc:{pack_id}"
            if not code.startswith(b"EDSENADDCONT") or not family or not title or tail or key in records:
                raise ValueError
            records[key] = (title.decode("utf-8"), description.decode("utf-8"))
    except ValueError as exc:
        raise ValueError(error) from exc
    return records
