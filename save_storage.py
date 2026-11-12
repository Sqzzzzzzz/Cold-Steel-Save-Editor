"""Inventory sessions and the file adapter for Cold Steel I on Steam."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
import re

from cs1 import SLOTS, Save
from item_catalog import CatalogItem


STEAM_SAVE_DIRECTORY = Path.home() / "Saved Games" / "Falcom" / "ed8"
SLOT_NAME = re.compile(r"(?:save\d{3}|autosave\d{2})\.dat", re.IGNORECASE)


@dataclass(frozen=True)
class Entry:
    slot: int
    item_id: int
    quantity: int


class InventorySession:
    def __init__(self, quantities: Mapping[int, int]):
        self.original_items = dict(quantities)
        self.quantities = self.original_items

    @property
    def changed(self) -> bool:
        return self.quantities != self.original_items

    @property
    def occupied_count(self) -> int:
        return len(self.quantities)

    def items(self) -> list[Entry]:
        return [
            Entry(slot, item_id, quantity)
            for slot, (item_id, quantity) in enumerate(self.quantities.items())
        ]


class SteamInventorySession(InventorySession):
    capacity = SLOTS

    def __init__(self, source: Path, save: Save):
        super().__init__(save.items)
        self.source = source
        self.original_bytes = save.original
        self.equipped_masters = frozenset(save.equipped_masters)
        try:
            self.modified_at = source.stat().st_mtime
        except OSError:
            self.modified_at = None


class SteamSaveStorage:
    def read(self, path: Path) -> SteamInventorySession:
        source = path.resolve()
        return SteamInventorySession(source, Save.open(source))

    def latest(self, directory: Path) -> SteamInventorySession:
        candidates = []
        if directory.is_dir():
            for path in directory.iterdir():
                if SLOT_NAME.fullmatch(path.name):
                    try:
                        candidates.append((path.stat().st_mtime_ns, path))
                    except FileNotFoundError:
                        continue
        for _, path in sorted(candidates, key=lambda entry: (entry[0], entry[1].name), reverse=True):
            try:
                return self.read(path)
            except (OSError, ValueError):
                continue
        raise FileNotFoundError("No compatible Cold Steel I Steam slots were found.")

    def save_copy(
        self, session: SteamInventorySession, destination: Path, catalog: Mapping[int, CatalogItem]
    ) -> Path:
        if not destination.suffix:
            destination = destination.with_suffix(".dat")
        if destination.suffix.lower() != ".dat":
            raise ValueError("Choose a .dat file for the save copy.")
        destination = destination.resolve()
        if destination == session.source:
            raise ValueError("Use Save with backup to replace the opened slot.")
        self._prepare(session, catalog).write(destination, original_path=False)
        return destination

    def overwrite(
        self, session: SteamInventorySession, catalog: Mapping[int, CatalogItem]
    ) -> tuple[SteamInventorySession, Path | None]:
        if session.source.suffix.lower() != ".dat":
            raise ValueError("Save a new .dat copy when a backup is open.")
        save = self._prepare(session, catalog)
        backup = save.write(session.source, original_path=True)
        return SteamInventorySession(session.source, Save(save.edited_bytes())), backup

    @staticmethod
    def _prepare(session: SteamInventorySession, catalog: Mapping[int, CatalogItem]) -> Save:
        save = Save(session.original_bytes)
        # Apply removals first so they free slots in a full inventory.
        for item_id in save.original_items.keys() - session.quantities.keys():
            if item_id not in catalog:
                raise ValueError("This item cannot be edited.")
            save.set_quantity(item_id, 0, catalog[item_id])
        for item_id, quantity in session.quantities.items():
            if save.original_items.get(item_id) != quantity:
                if item_id not in catalog:
                    raise ValueError("This item cannot be edited.")
                save.set_quantity(item_id, quantity, catalog[item_id])
        return save
