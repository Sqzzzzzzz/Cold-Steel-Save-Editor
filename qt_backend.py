"""Cold Steel I catalog and editor state for the Qt window."""

from collections import Counter, deque
import csv
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re

from PySide6.QtCore import QSettings

from item_catalog import CatalogItem, read_catalog
from save_storage import InventorySession, STEAM_SAVE_DIRECTORY, SteamInventorySession, SteamSaveStorage


STEAM_GAME = (
    Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)"))
    / "Steam/steamapps/common/Trails of Cold Steel"
)
ITEM_TABLE = Path("data/text/dat_us/t_item.tbl")
CYRILLIC = re.compile(r"[А-Яа-яЁё]")


@dataclass(frozen=True)
class ScanResult:
    root: Path
    files: tuple[Path, ...]
    items: dict[int, CatalogItem]
    errors: tuple[str, ...] = ()


def find_game_install(preferred: str = "") -> Path | None:
    candidates = [Path(preferred)] if preferred else []
    candidates.append(STEAM_GAME)
    return next((folder for folder in candidates if (folder / ITEM_TABLE).is_file()), None)


def scan_game_tables(root: Path) -> ScanResult:
    path = root / ITEM_TABLE
    if not path.is_file():
        raise FileNotFoundError("No readable item tables found")
    return ScanResult(root, (path,), read_catalog(path))


def category_for(item: CatalogItem) -> str:
    code = item.icon_type
    if 0x8C <= code <= 0x99:
        return "weapon"
    if 0xB5 <= code <= 0xB9:
        return "food"
    return {
        0x80: "material", 0x81: "consumable", 0x83: "recipe",
        0xA0: "armor", 0xA1: "shoes", 0xA2: "accessory", 0xA3: "costume",
        0xA4: "face", 0xAA: "quartz_normal", 0xAB: "quartz_master",
        0xB4: "ingredient", 0xC3: "book", 0xC4: "decoration",
        0xC9: "fishing_gear", 0xCA: "fishing_gear",
    }.get(code, {"key": "quest", "materials": "material", "items": "consumable"}.get(item.category, "other"))


class EditorCore:
    def __init__(
        self, game: Path | None = None, profile: QSettings | None = None,
        *, storage: SteamSaveStorage | None = None,
    ):
        self.storage = storage
        self.profile = profile if profile is not None else QSettings("ColdSteelSaveEditor", "ColdSteelI")
        try:
            self.settings = json.loads(self.profile.value("preview/preferences", "{}"))
        except (TypeError, ValueError):
            self.settings = {}
        if not isinstance(self.settings, dict):
            self.settings = {}
        self.settings["game_root"] = str(game or self.settings.get("game_root") or self.profile.value("game", ""))
        language = self.settings.get("language", "ru")
        self.language = language if language in ("ru", "en") else "ru"
        self.favorites = set(self.settings.get("favorites", []))
        self.recent = list(self.settings.get("recent", []))
        self.native: dict[int, CatalogItem] = {}
        self.catalog: dict[int, dict] = {}
        self.english: dict[int, dict] = {}
        self.save: InventorySession | None = None
        self.last_backup: Path | None = None
        self.undo_stack: deque[dict[int, int]] = deque(maxlen=20)
        self.last_scan: ScanResult | None = None
        self.persistence_warning = ""

    def _save_preferences(self):
        self.profile.setValue("preview/preferences", json.dumps(self.settings, ensure_ascii=False))
        self.profile.sync()
        self.persistence_warning = (
            "Unable to save preferences." if self.profile.status() != QSettings.Status.NoError else ""
        )

    def set_language(self, language: str):
        self.language = language
        self.settings["language"] = language
        self._save_preferences()

    def visible(self):
        return {item_id: record for item_id, record in self.catalog.items() if self.native[item_id].editable}

    def apply_scan_result(self, result: ScanResult):
        self.native = result.items
        self.catalog = {
            item_id: {
                "id": item_id, "name": item.name, "description": item.description,
                "category": category_for(item), "limit": item.limit,
                "_source": "dlc" if item.category == "dlc" else "base",
            }
            for item_id, item in self.native.items()
        }
        self.last_scan = result
        self.settings["game_root"] = str(result.root)
        if self.save is None and self.storage is None:
            self.load_demo()
        self._save_preferences()

    def load_demo(self) -> bool:
        if not self.native or self.storage is not None:
            return False
        counts = Counter()
        quantities = {}
        for item_id, record in sorted(self.visible().items()):
            category = record["category"]
            if counts[category] < (12 if category == "quartz_master" else 3):
                quantities[item_id] = min(record["limit"], max(1, 5 - counts[category]))
                counts[category] += 1
        self.save = InventorySession(quantities)
        self.last_backup = None
        self.undo_stack.clear()
        return True

    @property
    def source(self) -> Path | None:
        return self.save.source if isinstance(self.save, SteamInventorySession) else None

    @property
    def save_directory(self) -> Path:
        remembered = self.settings.get("save_directory")
        if remembered and Path(remembered).is_dir():
            return Path(remembered)
        return STEAM_SAVE_DIRECTORY

    def open_save(self, path: Path | None = None) -> Path:
        if self.storage is None:
            raise RuntimeError("Steam save operations are unavailable in sample mode.")
        session = self.storage.read(path) if path is not None else self.storage.latest(self.save_directory)
        self.save = session
        self.last_backup = None
        self.undo_stack.clear()
        self.settings["save_directory"] = str(session.source.parent)
        self._save_preferences()
        return session.source

    def save_copy(self, destination: Path) -> Path:
        if self.storage is None or not isinstance(self.save, SteamInventorySession):
            raise RuntimeError("No save loaded")
        return self.storage.save_copy(self.save, destination, self.native)

    def overwrite(self) -> Path | None:
        if self.storage is None or not isinstance(self.save, SteamInventorySession):
            raise RuntimeError("No save loaded")
        self.save, backup = self.storage.overwrite(self.save, self.native)
        self.last_backup = backup or self.last_backup
        self.undo_stack.clear()
        return backup

    def compare(self, path: Path) -> tuple[int, int, int]:
        if self.storage is None or not isinstance(self.save, SteamInventorySession):
            raise RuntimeError("No save loaded")
        other = self.storage.read(path).quantities
        current = self.save.quantities
        return (
            len(current.keys() - other.keys()),
            len(other.keys() - current.keys()),
            sum(current[item_id] != other[item_id] for item_id in current.keys() & other.keys()),
        )

    def import_english_catalog(self, source: str):
        path = Path(source)
        records = {
            item_id: {"name": item.name, "description": item.description}
            for item_id, item in read_catalog(path).items() if item.editable
        }
        if not records or sum(bool(CYRILLIC.search(row["name"])) for row in records.values()) > len(records) // 2:
            raise ValueError("Select an original English catalog. This file contains Russian or another language.")
        self.english = records
        return len(records)

    def item_name(self, item_id: int) -> str:
        record = self.catalog.get(item_id, {})
        english = self.english.get(item_id, {}) if self.language == "en" else {}
        return english.get("name") or record.get("name") or f"ID {item_id}"

    def details_text(self, item_id: int) -> str:
        record = self.catalog.get(item_id, {})
        english = self.english.get(item_id, {}) if self.language == "en" else {}
        return english.get("description") or record.get("description", "")

    def missing_translations(self) -> list[tuple[int, str]]:
        return [
            (item_id, record["name"])
            for item_id, record in self.visible().items()
            if bool(CYRILLIC.search(record["name"])) != (self.language == "ru")
            and not (self.language == "en" and item_id in self.english)
        ]

    def quantity(self, item_id: int) -> int:
        return self.save.quantities.get(item_id, 0) if self.save else 0

    def can_edit(self, item_id: int | None) -> bool:
        item = self.native.get(item_id)
        return bool(self.save and item and item.editable and not self.is_equipped_master(item_id))

    def is_equipped_master(self, item_id: int | None) -> bool:
        item = self.native.get(item_id)
        return bool(
            isinstance(self.save, SteamInventorySession) and item and item.category == "master"
            and item_id in self.save.equipped_masters
        )

    def can_delete(self, item_id: int | None) -> bool:
        return self.can_edit(item_id) and self.quantity(item_id) > 0

    def change(self, changes: dict[int, int]):
        if self.save is None:
            raise RuntimeError("Open a compatible save first")
        before = self.save.quantities
        candidate = before.copy()
        for item_id, quantity in changes.items():
            if self.is_equipped_master(item_id):
                raise ValueError("This Master Quartz is already equipped.")
            if not self.can_edit(item_id):
                raise ValueError("This item cannot be edited.")
            limit = self.native[item_id].limit
            if type(quantity) is not int or not 0 <= quantity <= limit:
                raise ValueError(f"Quantity must be between 0 and {limit}.")
            if quantity:
                candidate[item_id] = quantity
            else:
                candidate.pop(item_id, None)
        if isinstance(self.save, SteamInventorySession) and len(candidate) > self.save.capacity:
            raise ValueError("The inventory has no free slots.")
        if candidate != before:
            self.undo_stack.append(before)
            self.save.quantities = candidate
            self.recent = list(dict.fromkeys((*changes, *self.recent)))[:24]
            self._persist_lists()

    def undo(self) -> bool:
        if not self.save or not self.undo_stack:
            return False
        self.save.quantities = self.undo_stack.pop()
        return True

    def reset(self):
        if self.save:
            self.save.quantities = self.save.original_items
        self.undo_stack.clear()

    def toggle_favorite(self, item_id: int):
        self.favorites.symmetric_difference_update({item_id})
        self._persist_lists()

    def _persist_lists(self):
        self.settings.update(favorites=sorted(self.favorites), recent=self.recent)
        self._save_preferences()

    def export_csv(self, destination: str) -> Path:
        if self.save is None:
            raise RuntimeError("No save loaded")
        path = Path(destination)
        if not path.suffix:
            path = path.with_suffix(".csv")
        if path.suffix.lower() != ".csv":
            raise ValueError("Choose a .csv file for inventory export.")
        with path.open("x", newline="", encoding="utf-8-sig") as stream:
            writer = csv.writer(stream)
            writer.writerow(("ID", "Name", "Qty"))
            writer.writerows(
                (entry.item_id, self.item_name(entry.item_id), entry.quantity)
                for entry in self.save.items()
            )
        return path
