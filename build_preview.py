"""Build the Windows application from a clean checkout or with local artwork."""

import argparse
import os
from pathlib import Path
import subprocess
import sys

from version import VERSION


ROOT = Path(__file__).resolve().parent
NAME = "Cold_Steel_I_Inventory_Editor"
ART = (
    "heimdallr.jpg", "item-text.json",
    "thors.png", "logo.png", "item-atlas.png",
    "master-atlas.png", "menu-atlas.png", "fish-art.png", "fish-icons.png", "special-art.png",
    "arcus-cover-art.png", "shining-pom.png", "arrow-up.png", "arrow-down.png",
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--without-assets", action="store_true", help="Build without locally supplied game assets")
    parser.add_argument("--onefile", action="store_true", help="Bundle the runtime and resources into one executable")
    args = parser.parse_args()
    assets = ROOT / "assets"
    if not args.without_assets:
        missing = [name for name in ART if not (assets / name).is_file()]
        if missing:
            parser.error(f"Missing local assets: {', '.join(missing)}. See README.md.")

    system = Path(os.environ["SystemRoot"])
    environment = os.environ.copy()
    environment["PATH"] = os.pathsep.join(map(str, (Path(sys.executable).parent, system / "System32", system)))
    environment["PYINSTALLER_CONFIG_DIR"] = str(ROOT / "build/pyinstaller-cache")
    for key in ("PYTHONHOME", "PYTHONPATH", "QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH", "QML2_IMPORT_PATH"):
        environment.pop(key, None)
    build = ROOT / "build"
    build.mkdir(exist_ok=True)
    version_resource = build / "windows-version.txt"
    version_tuple = (*map(int, VERSION.split(".")), 0)
    version_resource.write_text(
        f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={version_tuple}, prodvers={version_tuple}, mask=0x3f,
    flags=0, OS=0x40004, fileType=0x1, subtype=0, date=(0, 0)),
  kids=[StringFileInfo([StringTable('040904B0', [
    StringStruct('FileDescription', 'Cold Steel I Inventory Editor'),
    StringStruct('FileVersion', '{VERSION}'),
    StringStruct('OriginalFilename', '{NAME}.exe'),
    StringStruct('ProductName', 'Cold Steel I Inventory Editor'),
    StringStruct('ProductVersion', '{VERSION}')
  ])]), VarFileInfo([VarStruct('Translation', [1033, 1200])])]
)""",
        encoding="utf-8",
    )
    mode = "--onefile" if args.onefile else "--onedir"
    dist = ROOT / "dist/onefile" if args.onefile else ROOT / "dist"
    work = build / ("onefile-pyinstaller" if args.onefile else "preview-pyinstaller")
    spec = work if args.onefile else build
    arguments = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", mode, "--windowed",
        "--name", NAME, "--specpath", str(spec), "--version-file", str(version_resource),
        "--workpath", str(work), "--distpath", str(dist),
    ]
    if args.onefile:
        notices = [ROOT / "LICENSE", Path(sys.base_prefix) / "LICENSE.txt",
                   *sorted((ROOT / "third_party").glob("*.txt")), ROOT / "third_party/README.md"]
        for notice in notices:
            arguments += ["--add-data", f"{notice};licenses"]
    if not args.without_assets:
        from PySide6.QtWidgets import QApplication
        from game_art import GameArt

        app = QApplication([])
        icon = GameArt().menu_icon("inventory")
        icon_path = build / "cs1-editor.ico"
        if icon.isNull() or not icon.pixmap(42, 42).save(str(icon_path), "ICO"):
            raise SystemExit("Could not prepare the original Windows application icon.")
        arguments += ["--icon", str(icon_path)]
        for name in ART:
            arguments += ["--add-data", f"{assets / name};assets"]
    subprocess.run([*arguments, str(ROOT / "app.py")], cwd=ROOT, env=environment, check=True)


if __name__ == "__main__":
    main()
