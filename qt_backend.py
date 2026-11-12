"""Cold Steel I catalog and an in-memory controller for the inherited Qt window."""

from collections import Counter, deque
import csv
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re

from PySide6.QtCore import QSettings

from item_catalog import CatalogItem, read_catalog
from save_storage import InventorySession, SaveStorage


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
    demo_mode = True
    storage: SaveStorage | None = None

    def __init__(self, game: Path | None = None, profile: QSettings | None = None):
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
        if self.save is None:
            self.load_demo()
        self._save_preferences()

    def load_demo(self) -> bool:
        if not self.native:
            return False
        counts = Counter()
        quantities = {}
        for item_id, record in sorted(self.visible().items()):
            category = record["category"]
            if counts[category] < (12 if category == "quartz_master" else 3):
                quantities[item_id] = min(record["limit"], max(1, 5 - counts[category]))
                counts[category] += 1
        self.save = InventorySession(quantities)
        self.undo_stack.clear()
        return True

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
        return bool(self.save and item and item.editable)

    def can_delete(self, item_id: int | None) -> bool:
        return self.can_edit(item_id) and self.quantity(item_id) > 0

    def change(self, changes: dict[int, int]):
        if self.save is None:
            raise RuntimeError("Open a compatible save first")
        before = self.save.quantities
        candidate = before.copy()
        for item_id, quantity in changes.items():
            if not self.can_edit(item_id):
                raise ValueError("This item cannot be edited.")
            limit = self.native[item_id].limit
            if type(quantity) is not int or not 0 <= quantity <= limit:
                raise ValueError(f"Quantity must be between 0 and {limit}.")
            if quantity:
                candidate[item_id] = quantity
            else:
                candidate.pop(item_id, None)
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
