from pathlib import Path
from struct import pack, pack_into
from tempfile import TemporaryDirectory
from unittest import TestCase

from cs1 import (
    CatalogItem, EMPTY_RECORD, INVENTORY_END, INVENTORY_OFFSET, ORBMENTS_OFFSET,
    RECORD, SAVE_HEADER, SAVE_SIZE, SLOTS, Save, read_catalog,
)


POTION = CatalogItem("Tear Balm", "Restores 800 HP", "items", 99, 0x81, 0)
MASTER = CatalogItem("Force", "", "master", 1, 0xAB, 3)


def make_save(*items: tuple[int, int]) -> bytes:
    data = bytearray(SAVE_SIZE)
    data[:len(SAVE_HEADER)] = SAVE_HEADER
    pack_into("<H", data, ORBMENTS_OFFSET, 2000)
    data[INVENTORY_OFFSET:INVENTORY_END] = (
        b"".join(RECORD.pack(item_id, quantity, bytes(32)) for item_id, quantity in items)
        + EMPTY_RECORD * (SLOTS - len(items))
    )
    data[-4:] = b"tail"
    return bytes(data)


class SaveTests(TestCase):
    def test_edit_roundtrip_changes_only_inventory(self):
        original = make_save((0, 2), (1, 3), (60000, 8))
        save = Save(original)
        self.assertEqual(save.edited_bytes(), original)
        save.set_quantity(0, 5, POTION)
        save.set_quantity(1, 0, POTION)
        save.set_quantity(2, 4, POTION)

        edited = save.edited_bytes()
        self.assertEqual(list(Save(edited).items.items()), [(0, 5), (60000, 8), (2, 4)])
        self.assertEqual(edited[:INVENTORY_OFFSET], original[:INVENTORY_OFFSET])
        self.assertEqual(edited[INVENTORY_END:], original[INVENTORY_END:])

    def test_undo_by_restoring_quantities_preserves_exact_bytes(self):
        original = make_save((0, 2), (1, 3))
        save = Save(original)
        save.set_quantity(0, 0, POTION)
        save.set_quantity(0, 2, POTION)
        self.assertFalse(save.changed)
        self.assertEqual(save.edited_bytes(), original)

    def test_invalid_quantity_and_equipped_master_are_rejected(self):
        save = Save(make_save((0, 2)))
        with self.assertRaisesRegex(ValueError, "between"):
            save.set_quantity(0, 100, POTION)
        with self.assertRaisesRegex(ValueError, "equipped"):
            save.set_quantity(2000, 1, MASTER)
        self.assertFalse(save.changed)

    def test_reject_wrong_game_duplicate_and_nonempty_after_padding(self):
        for data in (bytes(SAVE_SIZE), make_save((0, 1), (0, 2)), make_save((9999, 0), (0, 1))):
            with self.subTest(header=data[:8]), self.assertRaises(ValueError):
                Save(data)

    def test_writes_backup_and_refuses_to_overwrite_newer_source(self):
        original = make_save((0, 2))
        with TemporaryDirectory() as directory:
            path = Path(directory) / "save001.dat"
            path.write_bytes(original)
            save = Save.open(path)
            save.set_quantity(0, 5, POTION)
            backup = save.write(path, original_path=True)
            self.assertEqual(backup.read_bytes(), original)
            self.assertEqual(Save.open(path).items, {0: 5})
            with self.assertRaisesRegex(ValueError, "changed on disk"):
                save.write(path, original_path=True)
            self.assertEqual(Save.open(path).items, {0: 5})

    def test_new_copy_preserves_source(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "save001.dat"
            target = Path(directory) / "save002.dat"
            original = make_save((0, 2))
            source.write_bytes(original)
            save = Save.open(source)
            save.set_quantity(0, 3, POTION)
            self.assertIsNone(save.write(target, original_path=False))
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(Save.open(target).items, {0: 3})


class CatalogTests(TestCase):
    def test_reads_id_zero_and_actual_stack_limit_even_with_stale_record_length(self):
        metadata = bytearray(46)
        metadata[0] = 0x81
        metadata[39] = 7
        data = pack("<H", 1) + b"item\0\0\0" + bytes(4) + b"SL\0" + metadata
        data += b"Tear Balm\0#32IRestores 800 HP\0"
        with TemporaryDirectory() as directory:
            path = Path(directory) / "t_item.tbl"
            path.write_bytes(data)
            item = read_catalog(path)[0]
            self.assertEqual((item.name, item.description, item.limit), ("Tear Balm", "Restores 800 HP", 7))
            path.write_bytes(data[:-1])
            with self.assertRaises(ValueError):
                read_catalog(path)
