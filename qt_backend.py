"""Cold Steel I catalog and editor state for the Qt window."""

from collections import Counter, deque
import csv
from dataclasses import dataclass, field
from io import StringIO
import json
import os
from pathlib import Path
import re

from PySide6.QtCore import QSettings

from cs1 import publish_new, staged_file
from item_catalog import CatalogItem, ItemKey, NOTEBOOK_IDS, SEPITH_IDS, read_catalog, read_dlc_packs, read_fishing_notebook
from save_storage import InventorySession, STEAM_SAVE_DIRECTORY, SteamInventorySession, SteamSaveStorage


STEAM_GAME = (
    Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)"))
    / "Steam/steamapps/common/Trails of Cold Steel"
)
ITEM_TABLE = Path("data/text/dat_us/t_item.tbl")
FISH_TABLE = ITEM_TABLE.with_name("t_notefish.tbl")
DLC_TABLE = ITEM_TABLE.with_name("t_dlc.tbl")
ITEM_TEXT = Path(__file__).resolve().parent / "assets/item-text.json"
CYRILLIC = re.compile(r"[А-Яа-яЁё]")
NON_LATIN = re.compile(r"[А-Яа-яЁё\u3040-\u30ff\u3400-\u9fff]")
LATIN = re.compile(r"[A-Za-z]")


@dataclass(frozen=True)
class ScanResult:
    root: Path
    files: tuple[Path, ...]
    items: dict[int, CatalogItem]
    errors: tuple[str, ...] = ()
    translations: dict[str, dict[ItemKey, tuple[str, str]]] = field(default_factory=dict)
    fish: dict[str, tuple[str, str]] = field(default_factory=dict)
    dlc: dict[str, tuple[str, str]] = field(default_factory=dict)


def find_game_install(preferred: str = "") -> Path | None:
    candidates = [Path(preferred)] if preferred else []
    candidates.append(STEAM_GAME)
    for candidate in candidates:
        if (candidate / ITEM_TABLE).is_file():
            return candidate
    steam = STEAM_GAME.parents[2]
    if os.name == "nt":
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
                steam = Path(winreg.QueryValueEx(key, "SteamPath")[0])
        except OSError:
            pass
    candidates = [steam]
    try:
        libraries = (steam / "steamapps/libraryfolders.vdf").read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError):
        libraries = ""
    candidates.extend(Path(value.replace("\\\\", "\\")) for value in re.findall(r'"path"\s+"([^"]+)"', libraries))
    candidates = [library / "steamapps/common/Trails of Cold Steel" for library in candidates]
    return next((folder for folder in candidates if (folder / ITEM_TABLE).is_file()), None)


def scan_game_tables(root: Path) -> ScanResult:
    path = root / ITEM_TABLE
    if not path.is_file():
        raise FileNotFoundError("No readable item tables found")
    items = read_catalog(path)
    files = [path]
    errors = []
    references = []
    for relative, read in ((FISH_TABLE, read_fishing_notebook), (DLC_TABLE, read_dlc_packs)):
        source = root / relative
        records = {}
        if source.is_file():
            try:
                records = read(source)
                files.append(source)
            except (OSError, ValueError) as exc:
                errors.append(str(exc))
        references.append(records)
    fish, dlc = references
    try:
        translations = read_item_text()
    except (OSError, ValueError):
        translations = {}
        errors.append("The optional item translations could not be loaded.")
    return ScanResult(root, tuple(files), items, tuple(errors), translations, fish=fish, dlc=dlc)


def uses_language(text: str, language: str) -> bool:
    if language == "ru":
        return bool(CYRILLIC.search(text))
    return bool(LATIN.search(text) and not NON_LATIN.search(text))


def read_item_text() -> dict[str, dict[ItemKey, tuple[str, str]]]:
    if not ITEM_TEXT.is_file():
        return {}
    raw = json.loads(ITEM_TEXT.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Invalid item translations.")
    translations = {}
    for language in ("ru", "en"):
        entries = raw.get(language, {})
        if not isinstance(entries, dict):
            raise ValueError("Invalid item translations.")
        localized = {}
        for key, value in entries.items():
            if not isinstance(value, list) or len(value) != 2 or not all(isinstance(text, str) for text in value):
                raise ValueError("Invalid item translations.")
            if uses_language(value[0], language):
                localized[int(key) if key.isdecimal() else key] = tuple(value)
        translations[language] = localized
    return translations


def read_english_catalog(path: Path) -> dict[int, tuple[str, str]]:
    items = [item for item in read_catalog(path).items() if item[1].editable]
    records = {
        item_id: (item.name, item.description)
        for item_id, item in items
        if uses_language(item.name, "en") and (not item.description or uses_language(item.description, "en"))
    }
    if len(records) <= len(items) // 2:
        raise ValueError("Select an original English catalog. This file contains Russian or another language.")
    return records


def write_csv(path: Path, rows: list[tuple[int, str, int]], language: str = "en") -> Path:
    if not path.suffix:
        path = path.with_suffix(".csv")
    if path.suffix.lower() != ".csv":
        raise ValueError("Choose a .csv file for inventory export.")
    with StringIO(newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("ID", "Название", "Количество") if language == "ru" else ("ID", "Name", "Quantity"))
        for item_id, name, quantity in rows:
            if name.lstrip()[:1] in ("=", "+", "-", "@") or name.startswith(("\t", "\r", "\n")):
                name = "'" + name
            writer.writerow((item_id, name, quantity))
        with staged_file(path, stream.getvalue().encode("utf-8-sig")) as temporary:
            publish_new(temporary, path)
    return path


def saved_item_ids(value) -> list[int]:
    if not isinstance(value, list):
        return []
    return [i for i in value if type(i) is int and 0 <= i < 65536]


def category_for(item_id: int, item: CatalogItem) -> str:
    if item_id in (111, 154, 155, 156):
        return "card"
    if item_id in (174, 178):
        return "orbment"
    if item_id in (162, 255):
        return "fish_book"
    if item_id == 161 or item_id in NOTEBOOK_IDS or 323 <= item_id <= 340:
        return "book"
    code = item.icon_type
    if 0x8C <= code <= 0x99:
        return "weapon"
    if 0xB5 <= code <= 0xB9 or 26 <= item_id <= 37:
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
        root = self.settings.get("game_root") or self.profile.value("game", "")
        self.settings["game_root"] = str(game) if game is not None else root if isinstance(root, str) else ""
        language = self.settings.get("language", "ru")
        self.language = language if language in ("ru", "en") else "ru"
        self.favorites = set(saved_item_ids(self.settings.get("favorites")))
        self.recent = list(dict.fromkeys(saved_item_ids(self.settings.get("recent"))))[:24]
        self.native: dict[int, CatalogItem] = {}
        self.catalog: dict[ItemKey, dict] = {}
        self.english: dict[int, tuple[str, str]] = {}
        self.translations: dict[str, dict[ItemKey, tuple[str, str]]] = {}
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
        return {item_id: record for item_id, record in self.catalog.items() if record["listed"]}

    def apply_scan_result(self, result: ScanResult):
        self.native = result.items
        self.translations = result.translations
        self.catalog = {
            item_id: {
                "id": item_id, "name": item.name, "description": item.description,
                "category": category_for(item_id, item), "limit": item.limit, "listed": item.listed,
                "track_quantity": item_id not in SEPITH_IDS,
                # Shining Pom Bait and Suzaku also appear in the shop table.
                "_source": "both" if item_id in (25, 2192) else "dlc" if item.category == "dlc" else "base",
            }
            for item_id, item in self.native.items()
        }
        for category, source, entries in (("fish", "base", result.fish), ("dlc_pack", "dlc", result.dlc)):
            self.catalog.update({
                key: {"id": key, "name": name, "description": description, "category": category,
                      "listed": True, "track_quantity": False, "_source": source}
                for key, (name, description) in entries.items()
            })
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
        for item_id, item in sorted(self.native.items()):
            if not item.editable:
                continue
            record = self.catalog[item_id]
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
        if isinstance(remembered, str) and remembered and Path(remembered).is_dir():
            return Path(remembered)
        return STEAM_SAVE_DIRECTORY

    def read_save(self, path: Path | None = None) -> SteamInventorySession:
        if self.storage is None:
            raise RuntimeError("Steam save operations are unavailable in sample mode.")
        return self.storage.read(path) if path is not None else self.storage.latest(self.save_directory)

    def use_opened_save(self, session: SteamInventorySession) -> Path:
        self.save = session
        self.last_backup = None
        self.undo_stack.clear()
        self.settings["save_directory"] = str(session.source.parent)
        self._save_preferences()
        return session.source

    def use_overwritten_save(self, session: SteamInventorySession, backup: Path | None):
        self.save = session
        self.last_backup = backup or self.last_backup
        self.undo_stack.clear()

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

    def _item_text(self, item_id: ItemKey) -> tuple[str, str]:
        if self.language == "en" and item_id in self.english:
            return self.english[item_id]
        localized = self.translations.get(self.language, {}).get(item_id)
        if localized is not None:
            return localized
        record = self.catalog.get(item_id)
        if record and uses_language(record["name"], self.language):
            return record["name"], record["description"]
        return "", ""

    def item_name(self, item_id: ItemKey) -> str:
        name, _ = self._item_text(item_id)
        if not name and isinstance(item_id, str):
            category, _, number = item_id.partition(":")
            if category == "dlc":
                return f"Набор дополнения № {number}" if self.language == "ru" else f"DLC pack #{number}"
            return f"Запись рыбалки № {number}" if self.language == "ru" else f"Fishing record #{number}"
        return name or (f"Предмет № {item_id}" if self.language == "ru" else f"Item #{item_id}")

    def details_text(self, item_id: ItemKey) -> str:
        _, description = self._item_text(item_id)
        return description if uses_language(description, self.language) else ""

    def missing_translations(self) -> list[tuple[ItemKey, str]]:
        return [
            (item_id, self.item_name(item_id))
            for item_id in self.visible()
            if not self._item_text(item_id)[0]
        ]

    def quantity(self, item_id: ItemKey | None) -> int:
        return self.save.quantities.get(item_id, 0) if self.save else 0

    def can_edit(self, item_id: ItemKey | None) -> bool:
        item = self.native.get(item_id)
        return bool(self.save and item and item.editable and not self.is_equipped_master(item_id))

    def is_equipped_master(self, item_id: ItemKey | None) -> bool:
        item = self.native.get(item_id)
        return bool(
            isinstance(self.save, SteamInventorySession) and item and item.category == "master"
            and item_id in self.save.equipped_masters
        )

    def can_delete(self, item_id: ItemKey | None) -> bool:
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

    def export_rows(self) -> list[tuple[int, str, int]]:
        if self.save is None:
            raise RuntimeError("No save loaded")
        return [(item_id, self.item_name(item_id), quantity)
                for item_id, quantity in self.save.quantities.items()]
