"""Focused checks for the memory-only controller and the transplanted Qt window."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, skipUnless
from unittest.mock import patch

from PySide6.QtCore import QItemSelectionModel, QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from item_catalog import CatalogItem
from edit_changes import EditChanges
from qt_backend import EditorCore, ITEM_TABLE, STEAM_GAME, ScanResult, scan_game_tables
from qt_changes_dialog import ChangesDialog
from qt_window import MainWindow


class PreviewTests(TestCase):
    def test_batch_is_atomic_and_review_uses_the_original_sample(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            profile = QSettings(str(root / "settings.ini"), QSettings.Format.IniFormat)
            core = EditorCore(profile=profile)
            potion = CatalogItem("Tear Balm", "Restores 800 HP", "items", 99, 0x81, 0)
            master = CatalogItem("Force", "", "master", 1, 0xAB, 3)
            core.apply_scan_result(ScanResult(root, (), {0: potion, 2000: master}))
            self.assertIsNone(core.storage)
            initial = core.save.quantities.copy()
            with self.assertRaisesRegex(ValueError, "between 0 and 1"):
                core.change({0: 10, 2000: 2})
            self.assertEqual(core.save.quantities, initial)
            self.assertFalse(core.undo_stack)

            core.change({0: 10, 2000: 0})
            review = EditChanges()
            review.refresh(core.save)
            self.assertEqual(review.counts(), {"added": 0, "removed": 1, "modified": 1})
            self.assertTrue(core.undo())
            review.refresh(core.save)
            self.assertFalse(review.changes)
            self.assertEqual(core.save.quantities, initial)
            self.assertEqual([path.name for path in root.iterdir()], ["settings.ini"])


@skipUnless((STEAM_GAME / ITEM_TABLE).is_file(), "Cold Steel I Steam item table unavailable")
class NativeWindowTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle("Fusion")
        cls.scan = scan_game_tables(STEAM_GAME)

    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        profile = QSettings(str(Path(self.directory.name) / "settings.ini"), QSettings.Format.IniFormat)
        self.core = EditorCore(profile=profile)
        self.core.apply_scan_result(self.scan)
        self.window = MainWindow(self.core)
        self.window.initial_load_timer.stop()
        self.window.show()
        self.app.processEvents()
        self.addCleanup(self.close_window)

    def close_window(self):
        self.core.reset()
        self.window._quantity_user_edited = False
        self.window.close()
        self.app.processEvents()

    def test_tabs_search_sort_multiselection_and_language(self):
        window = self.window
        self.assertEqual(set(window.navigation), {"catalog", "inventory", "tools"})
        self.assertEqual(window.cat_table.rowCount(), len(self.core.visible()))
        window.cat_table.selectRow(0)
        self.assertEqual(window.active_item_id, 0)
        window.cat_search.setText("___no_item___")
        QTest.qWait(200)
        self.assertEqual(window.cat_table.rowCount(), 0)
        self.assertIsNone(window.active_item_id)
        self.assertFalse(window.apply_btn.isEnabled())
        window.cat_search.clear()
        QTest.qWait(200)

        window.sort_rows("catalog", 1)
        last_id = max(self.core.visible())
        self.assertEqual(window.cat_table.item(0, 0).data(Qt.ItemDataRole.UserRole), last_id)
        window.sort_rows("catalog", 1)
        flags = QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows
        for row in (0, 1):
            window.cat_table.selectionModel().select(window.cat_table.model().index(row, 0), flags)
        self.assertEqual(len(window.selected_ids(window.cat_table)), 2)
        self.assertTrue(window.bulk_bar.isVisible())
        window.add_one.click()
        self.assertEqual(self.core.quantity(0), 1)
        self.assertEqual(self.core.quantity(1), 1)
        window.undo_btn.click()
        self.assertEqual(self.core.quantity(0), self.core.save.original_items[0])

        window.cat_table.selectRow(0)
        window.qty.setValue(27)
        self.assertTrue(window.has_pending_quantity())
        window.cat_tree.setCurrentItem(window._category_nodes["catalog"]["quartz_master"])
        self.assertEqual(window.cat_table.rowCount(), 30)
        window.cat_table.selectRow(12)
        self.assertEqual(window.qty.maximum(), 1)
        self.assertFalse(window.has_pending_quantity())
        window.lang.setCurrentIndex(1)
        self.assertEqual(window.tabinv.text(), "My inventory")
        self.assertEqual(window.cat_table.horizontalHeaderItem(0).text(), "Item")
        window.tabinv.click()
        self.assertIs(window.pages.currentWidget(), window.invpage)
        window.navigation["tools"].click()
        self.assertIs(window.pages.currentWidget(), window.toolspage)
        self.assertFalse(window.detail.isVisible())

    def test_file_buttons_have_memory_only_previews(self):
        window = self.window
        self.core.change({0: 42})
        window.update_tables()
        dialog = ChangesDialog(window, "overwrite")
        self.assertEqual(dialog.table.rowCount(), 1)
        self.assertFalse(dialog.proceed.isEnabled())
        self.assertIn("Запись игровых файлов", dialog.note.text())
        with patch.object(window, "show_changes") as review:
            window.btn_overwrite.click()
            review.assert_called_with("overwrite")
            window.btn_savecopy.click()
            review.assert_called_with("copy")
        with patch.object(QMessageBox, "information") as compare:
            window.btn_compare.click()
            self.assertIn("Изменено: 1", compare.call_args.args[2])
        with (
            patch.object(QFileDialog, "getOpenFileName") as picker,
            patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No),
        ):
            window.btn_open.click()
            picker.assert_not_called()
        self.assertEqual(self.core.quantity(0), 42)
        self.assertEqual(list(Path(self.directory.name).glob("*.dat")), [])
