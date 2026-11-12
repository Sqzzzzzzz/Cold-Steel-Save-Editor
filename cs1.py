"""Binary inventory records for the Cold Steel I Steam save format."""

from contextlib import contextmanager
from datetime import datetime
import os
from pathlib import Path
from struct import Struct, unpack_from
from tempfile import NamedTemporaryFile

from item_catalog import CatalogItem, EMPTY_ID, read_catalog


SAVE_SIZE = 460992
SAVE_HEADER = bytes.fromhex("c0 08 07 00 08 00 00 00")
INVENTORY_OFFSET = 0x40C24
SLOTS = 4096
RECORD = Struct("<HH32s")
INVENTORY_END = INVENTORY_OFFSET + SLOTS * RECORD.size
EMPTY_RECORD = RECORD.pack(EMPTY_ID, 0, bytes(32))
ORBMENTS_OFFSET = 0x11C0
ORBMENT_SLOTS = 16
ORBMENT_SIZE = 18


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
        if (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
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
        """Publish a new copy or back up and replace the exact opened snapshot."""
        candidate = self.edited_bytes()
        Save(candidate)
        if not original_path:
            with staged_file(path, candidate) as temporary:
                publish_new(temporary, path)
            return None

        def verify_source():
            try:
                with path.open("rb") as stream:
                    current = stream.read(SAVE_SIZE + 1)
            except FileNotFoundError:
                current = None
            if current != self.original:
                raise ValueError("The source save changed on disk. Reopen it or save a copy.")

        verify_source()
        if candidate == self.original:
            return None

        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        backup = path.with_name(f"{path.name}.{stamp}.bak")
        with staged_file(path, candidate) as temporary:
            with staged_file(backup, self.original) as staged_backup:
                publish_new(staged_backup, backup)
            verify_source()
            os.replace(temporary, path)
        return backup


@contextmanager
def staged_file(destination: Path, data: bytes):
    temporary = None
    try:
        with NamedTemporaryFile(dir=destination.parent, prefix=f".{destination.name}.", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        yield temporary
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def publish_new(temporary: Path, destination: Path):
    if os.name == "nt":
        os.rename(temporary, destination)
    else:
        os.link(temporary, destination)
