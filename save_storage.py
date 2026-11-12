"""Inventory state and the boundary for a future Cold Steel I file adapter."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


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


class SaveStorage(Protocol):
    def read(self, path: Path) -> InventorySession: ...

    def write(self, path: Path, session: InventorySession, *, overwrite: bool) -> Path: ...
