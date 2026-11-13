"""Load the original Cold Steel I art or import it from a local game installation."""

import argparse
from functools import cache
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory

from PySide6.QtCore import QPoint, QRect, QRectF, Qt
from PySide6.QtGui import QIcon, QImage, QPainter, QPainterPath, QPixmap, QTransform

from item_catalog import CatalogItem


ASSETS = Path(__file__).resolve().parent / "assets"
SECTION_ICONS = {
    "all": 0x96, "equipment": 0x01, "quartz": 0x50, "master": 0x32,
    "materials": 0x27, "books": 0x16, "key": 0x4A, "dlc": 0x14, "items": 0x70,
}
BLADE_CARD_TILE = 0x100
RELIEF_CARD_TILE = 0x101
QUEST_DOCUMENT_TILE = 0x102
QUEST_TOOL_TILE = 0x103
GOLD_SALMON_TILE = 0x104
SHINING_POM_TILE = 0x105
SHINING_POM_BAIT_ID = 25
YELLOW_ORB_TILE = 0x91
SPECIAL_TILE_SIZE = 96
SPECIAL_TILE_FALLBACKS = (0x16, 0x16, 0x16, 0x4A)
FISH_TILE_START = 0x110
ARCUS_TILE_START = 0x130
ARCUS_COVER_IDS = (*range(2350, 2354), *range(2700, 2714), 2716)
ARCUS_COVER_TILES = {item_id: ARCUS_TILE_START + i for i, item_id in enumerate(ARCUS_COVER_IDS)}
ARCUS_DLC_COVERS = {
    11: 2700, 12: 2701, 13: 2702, 14: 2703,
    **dict(zip(range(59, 66), range(2704, 2711))),
    7001: 2711, 7003: 2712, 7011: 2716,
}
FOOD_TILES = {0xB5: 0x67, 0xB6: 0x68, 0xB7: 0x69, 0xB8: 0x6A, 0xB9: 0x6B}

# The PC table assigns the same item type to these distinct quest objects.
SPECIAL_ITEM_TILES = {
    100: 0x15, 101: 0x67, 102: QUEST_TOOL_TILE, 103: 0x11,
    104: 0x5C, 105: 0x5B, 106: 0x15, 107: 0x14, 108: 0x71,
    109: GOLD_SALMON_TILE, 110: QUEST_DOCUMENT_TILE, 111: BLADE_CARD_TILE,
    112: 0x15, 113: 0x15, 115: 0x5C, 116: 0x5B, 117: 0x15,
    118: 0x25, 119: 0x12, 121: QUEST_TOOL_TILE, 122: QUEST_TOOL_TILE,
    123: QUEST_DOCUMENT_TILE, 124: 0x72, 125: 0x27, 126: 0x15, 128: 0x48,
    **dict.fromkeys(range(129, 134), QUEST_DOCUMENT_TILE),
    134: 0x16, 135: QUEST_TOOL_TILE, 136: QUEST_TOOL_TILE, 137: 0x5F,
    139: 0x15, 140: 0x15, **dict.fromkeys(range(141, 146), 0x16),
    146: 0x15, 147: QUEST_TOOL_TILE, 148: 0x16,
    **dict.fromkeys(range(149, 154), QUEST_DOCUMENT_TILE),
    154: 0x14, 155: RELIEF_CARD_TILE, 156: 0xD4, 157: QUEST_TOOL_TILE,
    159: QUEST_DOCUMENT_TILE, 160: 0x16, 170: 0x54, 171: QUEST_DOCUMENT_TILE,
    174: YELLOW_ORB_TILE, 176: 0x27, 177: QUEST_DOCUMENT_TILE, 178: 0x92, 179: 0x16,
    **dict.fromkeys(range(180, 193), QUEST_DOCUMENT_TILE),
}
MENU_ICON_CENTERS = {
    "inventory": (665, 157), "catalog": (665, 413), "game": (665, 478),
    "open": (833, 210), "save": (833, 149), "remove": (833, 267),
}


class GameArt:
    def __init__(self):
        self.items = QPixmap(str(ASSETS / "item-atlas.png"))
        self.masters = QPixmap(str(ASSETS / "master-atlas.png"))
        self.menu = QPixmap(str(ASSETS / "menu-atlas.png"))
        self.fish = QPixmap(str(ASSETS / "fish-art.png"))
        self.fish_icons = QPixmap(str(ASSETS / "fish-icons.png"))
        self.special = QPixmap(str(ASSETS / "special-art.png"))
        self.arcus = QPixmap(str(ASSETS / "arcus-cover-art.png"))
        self.shining_pom = QPixmap(str(ASSETS / "shining-pom.png"))
        self.tiles = {}
        self.tile_icons = {}
        self.menu_icons = {}
        self.fish_tiles = {}

    def fish_picture(self, fish_id: int) -> QPixmap:
        if self.fish.isNull() or not 0 <= fish_id < 20:
            return self.tile(0x6D)
        if fish_id not in self.fish_tiles:
            self.fish_tiles[fish_id] = self.fish.copy(fish_id % 5 * 96, fish_id // 5 * 96, 96, 96)
        return self.fish_tiles[fish_id]

    def reference_tile(self, key: str) -> int:
        kind, _, number = key.partition(":")
        if kind == "fish":
            fish_id = int(number)
            return FISH_TILE_START + fish_id if 0 <= fish_id < 20 else 0x6D
        cover_id = ARCUS_DLC_COVERS.get(int(number))
        return ARCUS_COVER_TILES.get(cover_id, 0x14)

    def tile(self, index: int, master: bool = False) -> QPixmap:
        if not master and index == GOLD_SALMON_TILE:
            return self.fish_picture(14)
        if not master and index == SHINING_POM_TILE:
            return self.shining_pom if not self.shining_pom.isNull() else self.tile(SECTION_ICONS["items"])
        key = (index, master)
        if key not in self.tiles:
            if master:
                atlas, cell, columns = self.masters, 64, 8
            elif BLADE_CARD_TILE <= index <= QUEST_TOOL_TILE:
                index -= BLADE_CARD_TILE
                if self.special.isNull():
                    return self.tile(SPECIAL_TILE_FALLBACKS[index])
                atlas, cell, columns = self.special, SPECIAL_TILE_SIZE, len(SPECIAL_TILE_FALLBACKS)
            elif FISH_TILE_START <= index < FISH_TILE_START + 20:
                index -= FISH_TILE_START
                if self.fish_icons.isNull():
                    return self.tile(0x6D)
                atlas, cell, columns = self.fish_icons, 96, 5
            elif ARCUS_TILE_START <= index < ARCUS_TILE_START + len(ARCUS_COVER_IDS):
                index -= ARCUS_TILE_START
                if self.arcus.isNull():
                    return self.tile(0x72)
                atlas, cell, columns = self.arcus, 96, len(ARCUS_COVER_IDS)
            else:
                atlas, cell, columns = self.items, 32, 16
            self.tiles[key] = (QPixmap() if atlas.isNull() else
                               atlas.copy(index % columns * cell, index // columns * cell, cell, cell))
        return self.tiles[key]

    def tile_icon(self, index: int, master: bool = False) -> QIcon:
        key = (index, master)
        if key not in self.tile_icons:
            picture = self.tile(index, master)
            icon = QIcon(picture)
            if not picture.isNull():
                icon.addPixmap(picture, QIcon.Mode.Selected)
            self.tile_icons[key] = icon
        return self.tile_icons[key]

    def section_icon(self, category: str) -> QIcon:
        return self.tile_icon(SECTION_ICONS[category])

    def menu_icon(self, action: str) -> QIcon:
        if action in self.menu_icons:
            return self.menu_icons[action]
        if self.menu.isNull():
            return QIcon()
        x, y = MENU_ICON_CENTERS[action]
        source = self.menu.copy(x - 21, y - 21, 42, 42)
        circle = QPixmap(source.size())
        circle.fill(Qt.GlobalColor.transparent)
        painter = QPainter(circle)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        clip = QPainterPath()
        clip.addEllipse(QRectF(circle.rect()).adjusted(1, 1, -1, -1))
        painter.setClipPath(clip)
        painter.drawPixmap(0, 0, source)
        painter.end()
        icon = self.menu_icons[action] = QIcon(circle)
        return icon

    def item_icon(self, item_id: int, item: CatalogItem) -> QIcon:
        return self.tile_icon(*self._item_tile(item_id, item))

    def item_picture(self, item_id: int, item: CatalogItem) -> QPixmap:
        return self.tile(*self._item_tile(item_id, item))

    def _item_tile(self, item_id: int, item: CatalogItem) -> tuple[int, bool]:
        # The inventory atlas shares one bottle across medicines and EP charges.
        if item_id == SHINING_POM_BAIT_ID:
            return SHINING_POM_TILE, False
        if item_id in SPECIAL_ITEM_TILES:
            return SPECIAL_ITEM_TILES[item_id], False
        if item.icon_type == 0xC4:
            return ARCUS_COVER_TILES.get(item_id, 0x72), False
        if item.icon_type in FOOD_TILES:
            return FOOD_TILES[item.icon_type], False
        if 26 <= item_id <= 37:
            return 0x68, False
        if item.icon_type == 0xB4:
            return 0x15, False
        if item.icon_type == 0xC9:
            return 0x17, False
        if item.icon_type == 0xCA:
            return 0x6C, False
        if 241 <= item_id <= 247:
            return 0x20 + item_id - 241, False
        if item.category == "master" and 2000 <= item_id <= 2029 and not self.masters.isNull():
            return {2028: 26, 2029: 27}.get(item_id, item_id - 2000), True
        if item.category == "quartz" and 1 <= item.element <= 7:
            # The atlas has one row of element variants for each rarity.
            rarity = item.rarity if 0 <= item.rarity <= 2 else 0
            return (0x40, 0x50, 0x60)[rarity] + item.element - 1, False
        if item.category == "master" and 1 <= item.element <= 7:
            return 0x30 + item.element - 1, False
        if 0x8C <= item.icon_type <= 0xA4:
            return item.icon_type - (0x8B if item.icon_type < 0xA0 else 0x91), False
        return SECTION_ICONS[item.category], False


@cache
def shared_game_art() -> GameArt:
    return GameArt()


def _read_rgba_texture(path: Path, width: int, height: int) -> QImage:
    data = path.read_bytes()
    length = width * height * 4
    if not data.startswith(b"RYHP") or not 0 < len(data) - length < 8192:
        raise ValueError(f"Unrecognized Cold Steel I texture: {path.name}")
    if b"PTexture2D\0RGBA8\0" not in data[:-length]:
        raise ValueError(f"Unrecognized Cold Steel I texture format: {path.name}")
    texture = QImage(data[-length:], width, height, width * 4, QImage.Format.Format_RGBA8888)
    return texture.flipped(Qt.Orientation.Vertical)


def _import_special_art(extracted: Path, package: Path, senpatcher: Path) -> None:
    cards_package = package.with_name("I_MG002.pkg")
    if not cards_package.is_file():
        return
    cards_directory = extracted / "blade"
    cards_directory.mkdir()
    subprocess.run(
        [str(senpatcher.resolve()), "PKG.Extract", "-o", str(cards_directory), str(cards_package)], check=True,
    )
    cards = _read_rgba_texture(cards_directory / "min002cd.png.phyre", 512, 512)
    hud = _read_rgba_texture(extracted / "window2.png.phyre", 512, 512)
    sprites = (cards.copy(4, 3, 118, 158), cards.copy(388, 171, 120, 158),
               hud.copy(299, 19, 47, 35), hud.copy(227, 10, 53, 50))
    cell = SPECIAL_TILE_SIZE
    atlas = QImage(cell * len(sprites), cell, QImage.Format.Format_RGBA8888)
    atlas.fill(Qt.GlobalColor.transparent)
    painter = QPainter(atlas)
    for index, sprite in enumerate(sprites):
        if max(sprite.width(), sprite.height()) > cell - 8:
            sprite = sprite.scaled(cell - 8, cell - 8, Qt.AspectRatioMode.KeepAspectRatio,
                                   Qt.TransformationMode.SmoothTransformation)
        offset = QPoint(index * cell + (cell - sprite.width()) // 2, (cell - sprite.height()) // 2)
        painter.drawImage(offset, sprite)
    painter.end()
    if not atlas.save(str(ASSETS / "special-art.png")):
        raise OSError("Could not write special-art.png.")


def import_art(game: Path, senpatcher: Path) -> None:
    package = game / "data/asset/D3D11_us/I_SYSTEM.pkg"
    if not package.is_file():
        package = game / "data/asset/D3D11/I_SYSTEM.pkg"
    textures = (
        ("icons.png.phyre", "item-atlas.png", 512, 512),
        ("orbment_mq.png.phyre", "master-atlas.png", 512, 256),
        ("campmenu1.png.phyre", "menu-atlas.png", 1024, 1024),
    )
    with TemporaryDirectory() as directory:
        extracted = Path(directory)
        subprocess.run(
            [str(senpatcher.resolve()), "PKG.Extract", "-o", str(extracted), str(package)],
            check=True,
        )
        ASSETS.mkdir(exist_ok=True)
        for original, output, width, height in textures:
            upright = _read_rgba_texture(extracted / original, width, height)
            if not upright.save(str(ASSETS / output)):
                raise OSError(f"Could not write {output}.")
            if output == "item-atlas.png":
                # The original white menu cursor points right in tile 0xBE.
                cursor = upright.copy(457, 357, 19, 21)
                for direction, angle in (("up", -90), ("down", 90)):
                    filename = ASSETS / f"arrow-{direction}.png"
                    if not cursor.transformed(QTransform().rotate(angle)).save(str(filename)):
                        raise OSError(f"Could not write {filename.name}.")
        _import_special_art(extracted, package, senpatcher)

    logo = game / "data/system_us/savelogo.png"
    if logo.is_file() and not (ASSETS / "logo.png").exists():
        shutil.copyfile(logo, ASSETS / "logo.png")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("game", type=Path, help="Cold Steel I installation directory")
    parser.add_argument("senpatcher", type=Path, help="Path to SenPatcher.exe")
    args = parser.parse_args()
    import_art(args.game, args.senpatcher)
