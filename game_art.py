"""Load the original Cold Steel I art or import it from a local game installation."""

import argparse
from functools import cache
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QIcon, QImage, QPainter, QPainterPath, QPixmap, QTransform

from item_catalog import CatalogItem


ASSETS = Path(__file__).resolve().parent / "assets"
SECTION_ICONS = {
    "all": 0x96, "equipment": 0x01, "quartz": 0x50, "master": 0x32,
    "materials": 0x27, "books": 0x16, "key": 0x95, "dlc": 0x14, "items": 0x70,
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

    @cache
    def tile(self, index: int, master: bool = False) -> QPixmap:
        atlas, cell, columns = (self.masters, 64, 8) if master else (self.items, 32, 16)
        if atlas.isNull():
            return QPixmap()
        return atlas.copy(index % columns * cell, index // columns * cell, cell, cell)

    def section_icon(self, category: str) -> QIcon:
        return QIcon(self.tile(SECTION_ICONS[category]))

    def menu_icon(self, action: str) -> QIcon:
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
        return QIcon(circle)

    def item_icon(self, item_id: int, item: CatalogItem) -> QIcon:
        picture = self.item_picture(item_id, item)
        icon = QIcon(picture)
        icon.addPixmap(picture, QIcon.Mode.Selected)
        return icon

    def item_picture(self, item_id: int, item: CatalogItem) -> QPixmap:
        if item.category == "master" and 2000 <= item_id <= 2029 and not self.masters.isNull():
            return self.tile({2028: 26, 2029: 27}.get(item_id, item_id - 2000), master=True)
        if item.category in ("quartz", "master") and 1 <= item.element <= 7:
            return self.tile((0x50 if item.category == "quartz" else 0x30) + item.element - 1)
        if 0x8C <= item.icon_type <= 0xA4:
            return self.tile(item.icon_type - 0x8B if item.icon_type < 0xA0 else item.icon_type - 0x91)
        return self.tile(SECTION_ICONS[item.category])


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
            data = (extracted / original).read_bytes()
            length = width * height * 4
            if not data.startswith(b"RYHP") or not 0 < len(data) - length < 8192:
                raise ValueError(f"Unrecognized Cold Steel I texture: {original}")
            header = data[:-length]
            if b"PTexture2D\0RGBA8\0" not in header:
                raise ValueError(f"Unrecognized Cold Steel I texture format: {original}")
            texture = QImage(data[-length:], width, height, width * 4, QImage.Format.Format_RGBA8888)
            upright = texture.flipped(Qt.Orientation.Vertical)
            if not upright.save(str(ASSETS / output)):
                raise OSError(f"Could not write {output}.")
            if output == "item-atlas.png":
                # The original white menu cursor points right in tile 0xBE.
                cursor = upright.copy(457, 357, 19, 21)
                for direction, angle in (("up", -90), ("down", 90)):
                    filename = ASSETS / f"arrow-{direction}.png"
                    if not cursor.transformed(QTransform().rotate(angle)).save(str(filename)):
                        raise OSError(f"Could not write {filename.name}.")

    logo = game / "data/system_us/savelogo.png"
    if logo.is_file() and not (ASSETS / "logo.png").exists():
        shutil.copyfile(logo, ASSETS / "logo.png")
    steam_hero = game.parent.parent.parent / "appcache/librarycache/538680/library_hero.jpg"
    if steam_hero.is_file() and not (ASSETS / "hero.jpg").exists():
        shutil.copyfile(steam_hero, ASSETS / "hero.jpg")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("game", type=Path, help="Cold Steel I installation directory")
    parser.add_argument("senpatcher", type=Path, help="Path to SenPatcher.exe")
    args = parser.parse_args()
    import_art(args.game, args.senpatcher)
