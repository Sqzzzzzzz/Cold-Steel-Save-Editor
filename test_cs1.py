from pathlib import Path
import os
from struct import pack, pack_into
from tempfile import TemporaryDirectory
from unittest import TestCase, skipUnless
from unittest.mock import patch

from cs1 import (
    CatalogItem, EMPTY_RECORD, INVENTORY_END, INVENTORY_OFFSET, ORBMENTS_OFFSET,
    RECORD, SAVE_HEADER, SAVE_SIZE, SECOND_INVENTORY_END, SLOTS, Save, publish_new, read_catalog,
    replace_with_backup,
)
from save_storage import SteamSaveStorage
from item_catalog import read_dlc_packs, read_fishing_notebook


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
    data[INVENTORY_END:SECOND_INVENTORY_END] = EMPTY_RECORD * SLOTS
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
        equipped_and_owned = Save(make_save((2000, 1)))
        with self.assertRaisesRegex(ValueError, "equipped"):
            equipped_and_owned.set_quantity(2000, 0, MASTER)
        self.assertEqual(equipped_and_owned.items[2000], 1)

    def test_reject_wrong_game_duplicate_and_nonempty_after_padding(self):
        for data in (bytes(SAVE_SIZE), make_save((0, 1), (0, 2)), make_save((9999, 0), (0, 1))):
            with self.subTest(header=data[:8]), self.assertRaises(ValueError):
                Save(data)

    def test_rejects_invalid_records_in_the_second_inventory_block(self):
        item = RECORD.pack(0, 7, bytes(32))
        for records, error in (
            (EMPTY_RECORD + item, "Unrecognized inventory record"),
            (RECORD.pack(0, 0, bytes(32)), "Unrecognized inventory record"),
            (item + item, "Duplicate inventory ID"),
        ):
            with self.subTest(error=error, records=len(records)):
                data = bytearray(make_save((0, 2)))
                data[INVENTORY_END:INVENTORY_END + len(records)] = records
                with self.assertRaisesRegex(ValueError, error):
                    Save(bytes(data))

    def test_full_active_inventory_cannot_extend_into_the_second_block(self):
        source = bytearray(make_save(*((item_id, 1) for item_id in range(SLOTS))))
        source[INVENTORY_END:INVENTORY_END + RECORD.size] = RECORD.pack(0, 9, bytes(32))
        original = bytes(source)
        save = Save(original)
        with self.assertRaisesRegex(ValueError, "no free slots"):
            save.set_quantity(SLOTS, 1, POTION)
        save.set_quantity(SLOTS - 1, 2, POTION)
        edited = save.edited_bytes()
        self.assertEqual(edited[INVENTORY_END:], original[INVENTORY_END:])
        self.assertEqual(Save(edited).items[SLOTS - 1], 2)

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

    def test_existing_destination_is_left_untouched_by_save_copy(self):
        with TemporaryDirectory() as directory:
            destination = Path(directory) / "save002.dat"
            existing = make_save((0, 9))
            destination.write_bytes(existing)
            save = Save(make_save((0, 2)))
            with self.assertRaises(FileExistsError):
                save.write(destination, original_path=False)
            self.assertEqual(destination.read_bytes(), existing)
            self.assertEqual(list(Path(directory).iterdir()), [destination])

    def test_overwrite_rechecks_source_after_creating_backup(self):
        original = make_save((0, 2))
        newer = make_save((0, 9))
        with TemporaryDirectory() as directory:
            path = Path(directory) / "save001.dat"
            path.write_bytes(original)
            save = Save.open(path)
            save.set_quantity(0, 5, POTION)

            def publish_and_update(staged, backup):
                publish_new(staged, backup)
                path.write_bytes(newer)

            with patch("cs1.publish_new", side_effect=publish_and_update):
                with self.assertRaisesRegex(ValueError, "changed on disk"):
                    save.write(path, original_path=True)
            self.assertEqual(path.read_bytes(), newer)
            backup, = path.parent.glob("*.bak")
            self.assertEqual(backup.read_bytes(), original)

    @skipUnless(os.name == "nt", "Windows replacement semantics")
    def test_in_place_writer_is_blocked_during_replacement(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "save001.dat"
            original = make_save((0, 2))
            path.write_bytes(original)
            save = Save.open(path)
            save.set_quantity(0, 5, POTION)

            def competing_write(target, temporary, displaced):
                with self.assertRaises(PermissionError):
                    target.write_bytes(make_save((0, 9)))
                replace_with_backup(target, temporary, displaced)

            with patch("cs1.replace_with_backup", side_effect=competing_write):
                backup = save.write(path, original_path=True)
            self.assertEqual(backup.read_bytes(), original)
            self.assertEqual(Save.open(path).items, {0: 5})

    @skipUnless(os.name == "nt", "Windows replacement semantics")
    def test_concurrent_rename_is_preserved_for_recovery(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "save001.dat"
            original, concurrent = make_save((0, 2)), make_save((0, 9))
            path.write_bytes(original)
            rival = root / "rival.dat"
            rival.write_bytes(concurrent)
            save = Save.open(path)
            save.set_quantity(0, 5, POTION)

            def competing_rename(target, temporary, displaced):
                replace_with_backup(target, rival, root / "competing-original.dat")
                replace_with_backup(target, temporary, displaced)

            with patch("cs1.replace_with_backup", side_effect=competing_rename):
                with self.assertRaisesRegex(ValueError, "concurrent save was preserved"):
                    save.write(path, original_path=True)
            self.assertCountEqual([backup.read_bytes() for backup in root.glob("*.bak")], [original, concurrent])

    @skipUnless(os.name == "nt", "Windows replacement semantics")
    def test_failed_replacement_restores_a_displaced_slot(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "save001.dat"
            original = make_save((0, 2))
            path.write_bytes(original)
            save = Save.open(path)
            save.set_quantity(0, 5, POTION)

            def failed_after_displacement(target, temporary, displaced):
                os.rename(target, displaced)
                raise OSError("replacement failed")

            with patch("cs1.replace_with_backup", side_effect=failed_after_displacement):
                with self.assertRaisesRegex(OSError, "replacement failed"):
                    save.write(path, original_path=True)
            self.assertEqual(path.read_bytes(), original)
            self.assertTrue(all(backup.read_bytes() == original for backup in path.parent.glob("*.bak")))


class SteamStorageTests(TestCase):
    def test_latest_skips_incompatible_slots_and_sidecars(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            older = root / "save001.dat"
            latest = root / "autosave00.dat"
            invalid = root / "save511.dat"
            sidecar = root / "autosave00_t.dat"
            for index, path in enumerate((older, latest, invalid, sidecar), 1):
                path.write_bytes(b"not a slot" if path == invalid else make_save((0, index)))
                os.utime(path, (index, index))
            session = SteamSaveStorage().latest(root)
            self.assertEqual(session.source, latest.resolve())
            self.assertEqual(session.quantities, {0: 2})

    def test_new_game_plus_save_operations_preserve_the_second_block(self):
        data = bytearray(make_save((0, 2), (1, 3)))
        second_block = RECORD.pack(0, 9, bytes(32)) + RECORD.pack(8, 7, bytes(32))
        data[INVENTORY_END:INVENTORY_END + len(second_block)] = second_block
        original = bytes(data)
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "save001.dat"
            source.write_bytes(original)
            storage = SteamSaveStorage()

            session = storage.latest(root)
            self.assertEqual(session.quantities, {0: 2, 1: 3})
            self.assertEqual(session.capacity, 2048)
            unchanged = storage.save_copy(session, root / "unchanged.dat", {})
            self.assertEqual(unchanged.read_bytes(), original)

            session.quantities = {0: 5, 8: 4}
            catalog = dict.fromkeys((0, 1, 8), POTION)
            edited_copy = storage.save_copy(session, root / "edited.dat", catalog)
            self.assertEqual(source.read_bytes(), original)
            updated, backup = storage.overwrite(session, catalog)
            self.assertEqual(updated.quantities, {0: 5, 8: 4})
            self.assertEqual(backup.read_bytes(), original)
            for path in (edited_copy, source):
                edited = path.read_bytes()
                self.assertEqual(edited[:INVENTORY_OFFSET], original[:INVENTORY_OFFSET])
                self.assertEqual(edited[INVENTORY_END:], original[INVENTORY_END:])
                self.assertEqual(storage.read(path).quantities, {0: 5, 8: 4})

    def test_backup_can_be_restored_as_a_new_slot_without_mutating_it(self):
        original = make_save((0, 2), (60000, 8))
        with TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "save001.dat"
            target.write_bytes(original)
            storage = SteamSaveStorage()
            session = storage.read(target)
            session.quantities = {0: 7, 60000: 8}
            updated, backup = storage.overwrite(session, {0: POTION})
            self.assertFalse(updated.changed)
            self.assertEqual(updated.quantities, {0: 7, 60000: 8})
            self.assertEqual(backup.read_bytes(), original)
            restored = storage.read(backup)
            with self.assertRaisesRegex(ValueError, "backup is open"):
                storage.overwrite(restored, {0: POTION})
            copy = storage.save_copy(restored, root / "restored.dat", {})
            self.assertEqual(copy.read_bytes(), original)
            self.assertEqual(backup.read_bytes(), original)


class CatalogTests(TestCase):
    def test_dlc_packs_use_separate_ids_and_ignore_stale_record_lengths(self):
        header = b"dlc\0\0\0" + pack("<H", 25) + b"EDSENADDCONT0025\0EDSENNOKISEKIDLC\0"
        record = header + b"Free Trial Pack\0Includes healing items and quartz.\0"
        with TemporaryDirectory() as directory:
            path = Path(directory) / "t_dlc.tbl"
            path.write_bytes(pack("<H", 1) + record)
            self.assertEqual(read_dlc_packs(path), {"dlc:25": ("Free Trial Pack", "Includes healing items and quartz.")})
            for broken in (pack("<H", 1) + record[:-1], pack("<H", 2) + record * 2):
                path.write_bytes(broken)
                with self.assertRaisesRegex(ValueError, "Invalid Cold Steel I DLC table"):
                    read_dlc_packs(path)

    def test_fishing_notebook_uses_distinct_read_only_keys(self):
        def record(index, name, description):
            return b"QSFish\0\0\0" + pack("<H", index) + name + b"\0" + bytes(96) + description + b"\0"

        data = pack("<H", 2) + record(24, b"Record", b"") + record(0, b"Swordtail", b"A small fish.")
        with TemporaryDirectory() as directory:
            path = Path(directory) / "t_notefish.tbl"
            path.write_bytes(data)
            self.assertEqual(read_fishing_notebook(path), {"fish:0": ("Swordtail", "A small fish.")})
            path.write_bytes(data[:-1])
            with self.assertRaisesRegex(ValueError, "Invalid Cold Steel I fishing notebook"):
                read_fishing_notebook(path)

    def test_reads_id_zero_and_actual_stack_limit_even_with_stale_record_length(self):
        metadata = bytearray(46)
        metadata[0] = 0x81
        metadata[15:35] = pack("<10H", 12, 0, 0, 0, 0, 0, 3, 0, 200, 0)
        metadata[39] = 7
        data = pack("<H", 1) + b"item\0\0\0" + bytes(4) + b"SL\0" + metadata
        data += b"Tear Balm\0#32IRestores 800 HP\0"
        with TemporaryDirectory() as directory:
            path = Path(directory) / "t_item.tbl"
            path.write_bytes(data)
            item = read_catalog(path)[0]
            self.assertEqual((item.name, item.description, item.limit), ("Tear Balm", "Restores 800 HP", 7))
            self.assertEqual(item.stats, (12, 0, 0, 0, 0, 0, 3, 0, 200, 0))
            path.write_bytes(data[:-1])
            with self.assertRaisesRegex(ValueError, "Invalid Cold Steel I item table"):
                read_catalog(path)
            path.write_bytes(data.replace(b"Tear Balm", b"\xffear Balm"))
            with self.assertRaisesRegex(ValueError, "Invalid Cold Steel I item table"):
                read_catalog(path)
