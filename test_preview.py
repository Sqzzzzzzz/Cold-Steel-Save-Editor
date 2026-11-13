"""Focused checks for the memory-only controller and the transplanted Qt window."""

import os
from dataclasses import replace
from pathlib import Path
from struct import pack
from tempfile import TemporaryDirectory
from threading import Event
from unittest import TestCase, skipUnless
from unittest.mock import patch

from PySide6.QtCore import QItemSelectionModel, QPoint, QSettings, QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox, QStyle, QStyleOptionButton

from item_catalog import CatalogItem, NOTEBOOK_IDS
from game_art import BLADE_CARD_TILE, RELIEF_CARD_TILE, YELLOW_ORB_TILE
from edit_changes import EditChanges
from qt_backend import EditorCore, ITEM_TABLE, ITEM_TEXT, STEAM_GAME, ScanResult, find_game_install, scan_game_tables, uses_language, write_csv
from qt_changes_dialog import ChangesDialog
from qt_window import MainWindow
from save_storage import SteamSaveStorage
from test_cs1 import make_save


class PreviewTests(TestCase):
    def test_discovery_finds_game_in_a_secondary_steam_library(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            steam = root / "Steam"
            library = root / "Another Steam Library"
            (steam / "steamapps").mkdir(parents=True)
            game = library / "steamapps/common/Trails of Cold Steel"
            (game / ITEM_TABLE).parent.mkdir(parents=True)
            (game / ITEM_TABLE).touch()
            escaped = str(library).replace("\\", "\\\\")
            (steam / "steamapps/libraryfolders.vdf").write_text(f'"path" "{escaped}"', encoding="utf-8")
            default = steam / "steamapps/common/Trails of Cold Steel"
            with patch("qt_backend.STEAM_GAME", default):
                if os.name == "nt":
                    with patch("winreg.OpenKey", side_effect=OSError):
                        self.assertEqual(find_game_install(), game)
                else:
                    self.assertEqual(find_game_install(), game)

    def test_invalid_optional_translation_does_not_hide_the_game_catalog(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            table = root / ITEM_TABLE
            table.parent.mkdir(parents=True)
            metadata = bytearray(46)
            metadata[0], metadata[39] = 0x81, 99
            table.write_bytes(pack("<H", 1) + b"item\0\0\0" + bytes(4) + b"SL\0" + metadata
                              + b"Tear Balm\0Restores 800 HP\0")
            translations = root / "item-text.json"
            for content in ('{"ru":', '[]', '{"ru":{"0":["Missing description"]}}'):
                with self.subTest(content=content), patch("qt_backend.ITEM_TEXT", translations):
                    translations.write_text(content, encoding="utf-8")
                    result = scan_game_tables(root)
                    self.assertEqual(result.items[0].name, "Tear Balm")
                    self.assertFalse(result.translations)
                    self.assertIn("The optional item translations could not be loaded.", result.errors)

    def test_missing_translation_does_not_fall_back_to_another_language(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            profile = QSettings(str(root / "settings.ini"), QSettings.Format.IniFormat)
            core = EditorCore(profile=profile)
            items = {
                0: CatalogItem("Tear Balm", "Restores 800 HP", "items", 99, 0x81, 0),
                1: CatalogItem("Зелье", "Восстанавливает здоровье", "items", 99, 0x81, 0),
            }
            core.apply_scan_result(ScanResult(root, (), items))
            self.assertEqual(core.item_name(0), "Предмет № 0")
            self.assertEqual(core.details_text(0), "")
            self.assertEqual(core.item_name(1), "Зелье")
            core.set_language("en")
            self.assertEqual(core.item_name(0), "Tear Balm")
            self.assertEqual(core.item_name(1), "Item #1")
            self.assertEqual(core.details_text(1), "")

    def test_invalid_profile_fields_are_discarded(self):
        with TemporaryDirectory() as directory:
            profile = QSettings(str(Path(directory) / "settings.ini"), QSettings.Format.IniFormat)
            profile.setValue("preview/preferences", '{"favorites":null,"recent":[{},true,0,0,7],"save_directory":42}')
            core = EditorCore(profile=profile)
            self.assertEqual(core.favorites, set())
            self.assertEqual(core.recent, [0, 7])
            self.assertEqual(core.save_directory.name, "ed8")

    def test_csv_is_safe_to_open_and_refuses_to_replace_existing_file(self):
        with TemporaryDirectory() as directory:
            target = Path(directory) / "inventory.csv"
            write_csv(target, [(0, "Tear Balm", 3), (1, "  =1+1", 2)])
            data = target.read_bytes()
            self.assertIn("Tear Balm,3", data.decode("utf-8-sig"))
            self.assertIn("'  =1+1,2", data.decode("utf-8-sig"))
            with self.assertRaises(FileExistsError):
                write_csv(target, [(0, "Tear Balm", 8)])
            self.assertEqual(target.read_bytes(), data)
            self.assertEqual(list(target.parent.iterdir()), [target])

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


    def test_recent_items_records_additions_only(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            profile = QSettings(str(root / "settings.ini"), QSettings.Format.IniFormat)
            core = EditorCore(profile=profile)
            potion = CatalogItem("Potion", "Restores health", "items", 99, 0x81, 0)
            core.apply_scan_result(ScanResult(root, (), dict.fromkeys(range(4), potion)))
            self.assertEqual(set(core.save.quantities), {0, 1, 2})
            core.change({0: 0, 1: 9, 2: core.quantity(2), 3: 2})
            self.assertEqual(core.recent, [3])
            core.change({3: 5, 0: 2})
            self.assertEqual(core.recent, [0, 3])
            self.assertEqual(EditorCore(profile=profile).recent, [0, 3])


class CleanWindowTests(TestCase):
    def test_compact_table_headers_fit_in_both_languages(self):
        app = QApplication.instance() or QApplication([])
        with TemporaryDirectory() as directory:
            profile = QSettings(str(Path(directory) / "settings.ini"), QSettings.Format.IniFormat)
            window = MainWindow(EditorCore(profile=profile))
            window.initial_load_timer.stop()
            try:
                window.resize(1280, 720)
                window.show()
                for language in (0, 1):
                    window.lang.setCurrentIndex(language)
                    for section, table in (("catalog", window.cat_table), ("inventory", window.inv_table)):
                        window.navigate_section(section)
                        header = table.horizontalHeader()
                        for column in range(header.count()):
                            window.sort_rows(section, column)
                            app.processEvents()
                            with self.subTest(language=language, section=section, column=column):
                                self.assertGreaterEqual(table.columnWidth(column), header.sectionSizeHint(column))
            finally:
                window.close()
                app.processEvents()

    def test_catalog_and_language_switch_with_a_synthetic_table(self):
        app = QApplication.instance() or QApplication([])
        with TemporaryDirectory() as directory:
            root = Path(directory)
            profile = QSettings(str(root / "settings.ini"), QSettings.Format.IniFormat)
            core = EditorCore(profile=profile)
            potion = CatalogItem("Sample Potion", "Restores health", "items", 99, 0x81, 0)
            core.apply_scan_result(ScanResult(root, (), {0: potion}, translations={
                "ru": {0: ("Пробное зелье", "Восстанавливает здоровье")}
            }))
            window = MainWindow(core)
            window.initial_load_timer.stop()
            try:
                window.show()
                window.navigate_section("catalog")
                model = window.cat_table.model()
                window.cat_table.selectRow(0)
                self.assertEqual(model.index(0, 0).data(), "Пробное зелье")
                window.lang.setCurrentIndex(1)
                self.assertEqual(model.index(0, 0).data(), "Sample Potion")
                self.assertEqual(window.item_name.accessibleName(), "Sample Potion")
                window.cat_search.setText("unmatched")
                window.update_tables("catalog")
                self.assertEqual(model.rowCount(), 0)
                self.assertFalse(window.apply_btn.isEnabled())
            finally:
                window.close()
                app.processEvents()


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
        model = window.cat_table.model()
        self.assertEqual(model.rowCount(), len(self.core.visible()))
        window.cat_table.selectRow(0)
        self.assertEqual(window.active_item_id, 0)
        window.cat_search.setText("___no_item___")
        QTest.qWait(200)
        self.assertEqual(model.rowCount(), 0)
        self.assertIsNone(window.active_item_id)
        self.assertFalse(window.apply_btn.isEnabled())
        window.cat_search.clear()
        QTest.qWait(200)

        header = window.cat_table.horizontalHeader()
        point = QPoint(header.sectionViewportPosition(1) + 15, header.height() // 2)
        QTest.mouseClick(header.viewport(), Qt.MouseButton.LeftButton, pos=point)
        last_id = max(i for i in self.core.visible() if isinstance(i,int))
        self.assertEqual(model.index(0, 0).data(Qt.ItemDataRole.UserRole), last_id)
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
        self.assertEqual(model.rowCount(), 30)
        window.cat_table.selectRow(12)
        self.assertEqual(window.qty.maximum(), 1)
        self.assertFalse(window.has_pending_quantity())
        window.lang.setCurrentIndex(1)
        self.assertEqual(window.tabinv.text(), "My inventory")
        self.assertEqual(model.headerData(0, Qt.Orientation.Horizontal), "Item")
        window.tabinv.click()
        self.assertIs(window.pages.currentWidget(), window.invpage)
        window.navigation["tools"].click()
        self.assertIs(window.pages.currentWidget(), window.toolspage)
        self.assertFalse(window.detail.isVisible())

    @skipUnless(ITEM_TEXT.is_file(), "Local bilingual item text unavailable")
    def test_all_catalog_items_and_selected_item_use_the_current_language(self):
        window = self.window
        table = window.cat_table
        table.selectRow(0)
        item_ids = tuple(i for i, item in self.core.native.items() if item.editable)
        self.assertEqual(window.active_item_id, 0)
        self.assertEqual(window.item_name.accessibleName(), "Зелье «Тиа»")
        self.assertIn("ОЗ", window.description.toPlainText())
        self.assertEqual(window.source_actions[2].text(), "Дополнения")
        self.assertEqual(self.core.item_name(2145), "Здоровье 1")
        self.assertEqual(self.core.item_name(254), "Книга рецептов")
        self.assertEqual(self.core.item_name(1512), "Квартетный пудинг")
        self.assertFalse(self.core.missing_translations())
        self.assertTrue(all(uses_language(self.core.item_name(i), "ru") and
                            uses_language(self.core.details_text(i), "ru") for i in item_ids))
        window.cat_search.setText("Тиа")
        QTest.qWait(150)
        self.assertTrue(table.model().index_for_id(0).isValid())
        window.cat_search.clear()
        window.lang.setCurrentIndex(1)
        self.assertEqual(window.active_item_id, 0)
        self.assertEqual(window.item_name.accessibleName(), "Tear Balm")
        self.assertIn("HP", window.description.toPlainText())
        self.assertEqual(window.source_actions[2].text(), "DLC")
        self.assertEqual(self.core.item_name(254), "Recipe Book")
        self.assertIn("high-purity amberl", self.core.details_text(630))
        self.assertFalse(self.core.missing_translations())
        self.assertTrue(all(uses_language(self.core.item_name(i), "en") and
                            uses_language(self.core.details_text(i), "en") for i in item_ids))

    def test_catalog_shows_game_entries_without_an_inventory(self):
        window = self.window
        self.core.save = None
        window.populate_categories()
        window.update_tables()
        window.navigate_section("catalog")
        nodes = window._category_nodes["catalog"]
        model = window.cat_table.model()
        self.assertEqual(model.rowCount(), len(self.core.visible()))
        self.assertEqual(nodes["all"].text(1), str(model.rowCount()))
        self.assertNotIn("hair", nodes)
        self.assertTrue(nodes["other"].isHidden())

        for category, ids in (("card", {111,154,155,156}), ("orbment", {174,178}), ("fish_book", {162,255})):
            window.cat_tree.setCurrentItem(nodes[category])
            self.assertEqual({row.item_id for row in model.rows}, ids)
        for category, ids in (("food", range(26, 38)), ("book", (161, *range(323, 341)))):
            window.cat_tree.setCurrentItem(nodes[category])
            self.assertTrue(set(ids).issubset(row.item_id for row in model.rows))
        window.cat_tree.setCurrentItem(nodes["material"])
        self.assertEqual(model.rowCount(), 12)
        window.cat_table.selectRow(model.index_for_id(241).row())
        self.assertEqual(window.qty.text(), "—")
        self.assertFalse(window.apply_btn.isEnabled())
        self.assertFalse(self.core.native[109].editable)

        if self.scan.fish:
            window.cat_tree.setCurrentItem(nodes["fish"])
            self.assertEqual(model.rowCount(), 20)
            window.cat_table.selectRow(model.index_for_id("fish:0").row())
            self.assertEqual(window.id_field.text(), "—")
            self.assertEqual(window.qty.text(), "—")
            self.assertFalse(window.apply_btn.isEnabled())
            self.assertFalse(window.favorite_btn.isEnabled())
            window.lang.setCurrentIndex(1)
            self.assertEqual(window.item_name.accessibleName(), "Swordtail")
            self.assertIn("Fishing notebook", window.quantity_note.toolTip())
            window.missing.setChecked(True)
            self.assertEqual(model.rowCount(), 0)
            self.assertTrue(window.catalog_empty.isVisible())
            window.missing.setChecked(False)
            self.assertEqual(model.rowCount(), 20)

    def test_notebook_tabs_use_the_game_book_icon_and_are_read_only(self):
        window = self.window
        model = window.cat_table.model()
        book_icon = window.art.tile_icon(0x16)
        if book_icon.isNull():
            self.skipTest("Cold Steel I item art unavailable")
        for item_id in (161, 162, *NOTEBOOK_IDS):
            index = model.index_for_id(item_id)
            self.assertTrue(index.isValid())
            self.assertEqual(index.data(Qt.ItemDataRole.DecorationRole).cacheKey(), book_icon.cacheKey())
        self.assertTrue(self.core.can_edit(161))
        self.assertTrue(all(not self.core.can_edit(item_id) for item_id in NOTEBOOK_IDS))
        window.cat_table.selectRow(model.index_for_id(254).row())
        self.assertFalse(window.apply_btn.isEnabled())
        self.assertIn("Служебная вкладка блокнота", window.quantity_note.toolTip())
        window.lang.setCurrentIndex(1)
        self.assertIn("Notebook tab", window.quantity_note.toolTip())
        self.assertFalse(window.big_icon.pixmap().isNull())

    def test_special_items_have_appropriate_game_icons_instead_of_chests(self):
        window = self.window
        art = window.art
        chest = art.tile_icon(0x95)
        if chest.isNull():
            self.skipTest("Cold Steel I item art unavailable")
        model = window.cat_table.model()
        window.cat_tree.setCurrentItem(window._category_nodes["catalog"]["special"])
        self.assertTrue(model.index_for_id(114).isValid())
        for row in range(model.rowCount()):
            icon = model.index(row, 0).data(Qt.ItemDataRole.DecorationRole)
            self.assertFalse(icon.isNull())
            self.assertNotEqual(icon.cacheKey(), chest.cacheKey())
        for item_id, tile in ((111, BLADE_CARD_TILE), (154, 0x14), (155, RELIEF_CARD_TILE),
                              (156, 0xD4), (174, YELLOW_ORB_TILE), (178, 0x92)):
            index = model.index_for_id(item_id)
            self.assertEqual(index.data(Qt.ItemDataRole.DecorationRole).cacheKey(), art.tile_icon(tile).cacheKey())

    def test_dlc_packs_keep_inventory_ids_and_source_filter_distinct(self):
        if not self.scan.dlc:
            self.skipTest("Cold Steel I DLC table unavailable")
        window = self.window
        nodes = window._category_nodes["catalog"]
        model = window.cat_table.model()
        window.cat_tree.setCurrentItem(nodes["dlc_pack"])
        self.assertEqual({row.item_id for row in model.rows}, set(self.scan.dlc))
        window.cat_table.selectRow(model.index_for_id("dlc:25").row())
        self.assertEqual(window.id_field.text(), "—")
        self.assertEqual(window.qty.text(), "—")
        self.assertFalse(window.apply_btn.isEnabled())
        self.assertFalse(window.favorite_btn.isEnabled())
        window.lang.setCurrentIndex(1)
        self.assertEqual(window.item_name.accessibleName(), "Free Trial Pack")
        self.assertIn("DLC pack", window.quantity_note.toolTip())
        window.cat_tree.setCurrentItem(nodes["all"])
        window.source.setCurrentIndex(2)
        expected = {item_id for item_id, item in self.scan.items.items() if item.listed and item.category == "dlc"}
        self.assertEqual({row.item_id for row in model.rows}, expected | {25, 2192} | self.scan.dlc.keys())
        window.source.setCurrentIndex(1)
        self.assertTrue({25, 2192}.issubset(row.item_id for row in model.rows))
        self.assertFalse(model.index_for_id("dlc:25").isValid())

    def test_item_preview_uses_whole_pixels_when_enlarged(self):
        window = self.window
        original = window.art.item_picture(0, self.scan.items[0])
        if original.isNull():
            self.skipTest("Cold Steel I item art unavailable")
        window._set_big_icon(0, 90)
        preview = window.big_icon.pixmap()
        self.assertEqual(preview.width() % original.width(), 0)
        factor = preview.width() // original.width()
        source = original.toImage()
        enlarged = preview.toImage()
        for y in range(source.height()):
            for x in range(source.width()):
                self.assertEqual(enlarged.pixel(x * factor, y * factor), source.pixel(x, y))

    def test_item_icons_follow_quartz_rarity_and_inventory_types(self):
        art = self.window.art
        if art.items.isNull():
            self.skipTest("Cold Steel I item art unavailable")
        expected = {
            2100: 0x40, 2122: 0x50, 2287: 0x65,
            1500: 0x6A, 1520: 0x67, 1540: 0x68, 1560: 0x69, 1575: 0x6B,
            1600: 0x15, 201: 0x17, 220: 0x6C,
        }
        for item_id, tile in expected.items():
            self.assertEqual(self.window._icon(item_id).cacheKey(), art.tile_icon(tile).cacheKey(), item_id)

    def test_consumables_use_shared_game_bottle_and_pom_notebook_art(self):
        window = self.window
        art = window.art
        bottle = art.tile_icon(0x70)
        if bottle.isNull() or art.shining_pom.isNull():
            self.skipTest("Cold Steel I consumable art unavailable")
        window.cat_tree.setCurrentItem(window._category_nodes["catalog"]["consumable"])
        model = window.cat_table.model()
        self.assertEqual({row.item_id for row in model.rows}, set(range(26)))
        for item_id in range(25):
            icon = model.index_for_id(item_id).data(Qt.ItemDataRole.DecorationRole)
            self.assertEqual(icon.cacheKey(), bottle.cacheKey(), item_id)
        bait = model.index_for_id(25)
        self.assertNotEqual(bait.data(Qt.ItemDataRole.DecorationRole).cacheKey(), bottle.cacheKey())
        self.assertEqual(art.item_picture(25, self.scan.items[25]).cacheKey(), art.shining_pom.cacheKey())
        window.cat_table.selectRow(bait.row())
        self.assertIn("боевого блокнота", window.big_icon.toolTip())
        window.lang.setCurrentIndex(1)
        self.assertIn("battle notebook", window.big_icon.toolTip())

    def test_fish_and_arcus_covers_use_matching_original_art(self):
        window = self.window
        art = window.art
        if art.fish_icons.isNull() or art.arcus.isNull():
            self.skipTest("Cold Steel I fish and ARCUS art unavailable")
        self.assertEqual(len({window._icon(f"fish:{i}").cacheKey() for i in range(20)}), 20)
        self.assertNotEqual(window._icon(2700).cacheKey(), window._icon(2701).cacheKey())
        self.assertEqual(window._icon(2700).cacheKey(), window._icon("dlc:11").cacheKey())
        self.assertEqual(art.item_picture(2700, self.scan.items[2700]).width(), 96)

    def test_missing_checkbox_shows_a_tick_and_still_toggles_the_filter(self):
        checkbox = self.window.missing
        option = QStyleOptionButton()
        checkbox.initStyleOption(option)
        indicator = checkbox.style().subElementRect(QStyle.SubElement.SE_CheckBoxIndicator, option, checkbox)
        unchecked = checkbox.grab(indicator).toImage()
        count = self.window.cat_table.model().rowCount()
        QTest.mouseClick(checkbox, Qt.MouseButton.LeftButton, pos=indicator.center())
        self.assertTrue(checkbox.isChecked())
        self.assertLess(self.window.cat_table.model().rowCount(), count)
        checkbox.initStyleOption(option)
        self.assertEqual(checkbox.style().subElementRect(QStyle.SubElement.SE_CheckBoxIndicator, option, checkbox), indicator)
        checked = checkbox.grab(indicator).toImage()
        dpr = checkbox.devicePixelRatioF()
        margin = round(3 * dpr)
        interior = [(x, y) for y in range(margin, checked.height() - margin)
                    for x in range(margin, checked.width() - margin)]
        self.assertTrue(all(unchecked.pixelColor(x, y).lightness() < 100 for x, y in interior))
        self.assertGreater(sum(checked.pixelColor(x, y).lightness() > 215 for x, y in interior), 8)
        QTest.keyClick(checkbox, Qt.Key.Key_Space)
        self.assertFalse(checkbox.isChecked())
        self.assertEqual(self.window.cat_table.model().rowCount(), count)

    def test_category_sort_and_tabs_preserve_selection_where_visible(self):
        window = self.window
        table = window.cat_table
        model = table.model()
        nodes = window._category_nodes["catalog"]
        self.core.toggle_favorite(0)
        table.verticalScrollBar().setValue(600)
        window.cat_tree.setCurrentItem(nodes["consumable"])
        self.assertEqual(table.verticalScrollBar().value(), 0)
        nodes["equipment"].setExpanded(False)
        window.cat_quick_favorite.click()
        self.assertEqual(model.rowCount(), 1)
        self.assertEqual(model.index(0, 0).data(Qt.ItemDataRole.UserRole), 0)
        self.assertFalse(window.cat_tree.selectedItems())
        window.cat_tree.setCurrentItem(nodes["consumable"])
        self.assertFalse(window.cat_quick_favorite.isChecked())
        self.assertGreater(model.rowCount(), 1)
        window.cat_quick_favorite.click()
        window.cat_quick_favorite.click()
        self.assertEqual(window.cat_tree.selectedItems(), [nodes["consumable"]])
        window.cat_tree.setCurrentItem(nodes["all"])
        table.selectRow(100)
        selected_id = window.active_item_id
        table.verticalScrollBar().setValue(90)
        top_id = model.index(table.rowAt(0), 0).data(Qt.ItemDataRole.UserRole)
        window.sort_rows("catalog", 1)
        self.assertEqual(window.active_item_id, selected_id)
        self.assertEqual(model.index(table.rowAt(0), 0).data(Qt.ItemDataRole.UserRole), top_id)
        window.lang.setCurrentIndex(1)
        self.assertFalse(nodes["equipment"].isExpanded())
        window.tabinv.click()
        self.assertIsNone(window.active_item_id)
        self.assertFalse(window.favorite_btn.isEnabled())
        self.assertIn("Select an item", window.description.toPlainText())
        window.tabcat.click()
        self.assertEqual(window.active_item_id, selected_id)

    def test_item_details_and_quantity_buttons(self):
        window = self.window
        table = window.cat_table
        table.selectRow(0)
        self.assertEqual(window.id_field.text(), "0")
        self.assertIn("99", window.qty_caption.toolTip())
        self.assertFalse(window.apply_btn.isEnabled())
        window.qty.setValue(27)
        window.lang.setCurrentIndex(1)
        self.assertEqual(window.qty.value(), 27)
        self.assertTrue(window.has_pending_quantity())
        self.assertTrue(window.apply_btn.isEnabled())
        window.apply_btn.click()
        self.assertEqual(self.core.quantity(0), 27)
        self.assertFalse(window.apply_btn.isEnabled())
        window.delete_btn.click()
        self.assertEqual(self.core.quantity(0), 0)
        self.assertFalse(window.delete_btn.isEnabled())
        window.undo_btn.click()
        self.assertEqual(self.core.quantity(0), 27)
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            window.reset_btn.click()
        self.assertEqual(self.core.quantity(0), self.core.save.original_items[0])
        self.assertFalse(window.reset_btn.isEnabled())

        item_id = next(i for i, item in self.core.native.items() if item.editable and item.stats and item.stats[0])
        table.selectRow(table.model().index_for_id(item_id).row())
        item = self.core.native[item_id]
        description = self.core.details_text(item_id)
        self.assertTrue(description)
        self.assertIn(description.strip(), window.description.toPlainText())
        self.assertIn(f"STR +{item.stats[0]}", window.description.toPlainText())
        self.assertFalse(window.big_icon.pixmap().isNull())
        for item_id, stat in ((120, "ACC +20%"), (1001, "EVA +5%")):
            table.selectRow(table.model().index_for_id(item_id).row())
            self.assertIn(stat, window.description.toPlainText())

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

    def test_overwrite_keeps_gui_responsive_and_preserves_pending_quantity(self):
        entered = Event()
        release = Event()

        class GatedStorage(SteamSaveStorage):
            def overwrite(self, session, catalog):
                entered.set()
                if not release.wait(2):
                    raise TimeoutError("The GUI did not release the background write.")
                return super().overwrite(session, catalog)

        window = self.window
        self.core.storage = GatedStorage()
        target = Path(self.directory.name) / "save001.dat"
        original = make_save((0, 4), (1, 2))
        target.write_bytes(original)
        self.assertTrue(window.open_save(target))
        self.wait_for_file_job()
        self.assertEqual(self.core.source, target)
        window.tabcat.click()
        window.cat_table.selectRow(0)
        self.core.change({0: 6, 1: 0, 4: 1})
        window.update_tables()
        window.show_item(0)
        window.qty.setValue(12)
        with patch.object(window, "show_changes", return_value=True):
            window.btn_overwrite.click()
        try:
            self.assertTrue(entered.wait(1))
            self.assertFalse(window.qty.isEnabled())
            self.assertFalse(window.btn_overwrite.isEnabled())
            self.assertFalse(window.open_save(target))
            self.assertEqual(target.read_bytes(), original)
            window.lang.setCurrentIndex(1)
            self.assertEqual(window.qty.value(), 12)
            QTimer.singleShot(20, release.set)
            self.wait_for_file_job()
        finally:
            release.set()
        self.assertEqual(self.core.save.quantities, {0: 6, 4: 1})
        self.assertEqual(self.core.last_backup.read_bytes(), original)
        self.assertEqual(self.core.compare(self.core.last_backup), (1, 1, 1))
        self.assertEqual(window.qty.value(), 12)
        self.assertTrue(window.has_pending_quantity())
        self.assertTrue(window.apply_btn.isEnabled())

    def test_closing_during_compare_does_not_open_a_result_dialog(self):
        window = self.window
        release = Event()

        def compare():
            release.wait(1)
            return 0, 0, 0

        self.assertTrue(window._run_file(compare, window._show_comparison))
        with patch.object(QMessageBox, "information") as report:
            self.assertFalse(window.close())
            release.set()
            self.wait_for_file_job()
            QTest.qWait(15)
            report.assert_not_called()
            self.assertFalse(window.isVisible())

    def test_overwrite_uses_catalog_snapshot_from_the_review(self):
        window = self.window
        self.core.storage = SteamSaveStorage()
        target = Path(self.directory.name) / "save001.dat"
        target.write_bytes(make_save((0, 4)))
        window.open_save(target)
        self.wait_for_file_job()
        self.core.change({0: 6})
        window.update_tables()
        release = Event()
        window._file_pool.submit(release.wait, 2)
        try:
            with patch.object(window, "show_changes", return_value=True):
                window.btn_overwrite.click()
            new_items = self.core.native | {0: replace(self.core.native[0], limit=5)}
            self.core.apply_scan_result(replace(self.scan, items=new_items))
            window.refresh_catalog()
        finally:
            release.set()
        self.wait_for_file_job()
        self.assertEqual(self.core.storage.read(target).quantities, {0: 6})

    def wait_for_file_job(self):
        for _ in range(100):
            if self.window._file_job is None:
                return
            QTest.qWait(15)
        self.fail("Background file job did not finish.")
