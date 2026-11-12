"""Build the local Windows preview in an isolated DLL search environment."""

import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parent
NAME = "Cold_Steel_I_Inventory_Editor"
ART = (
    "hero.jpg", "academy-full.jpg", "thors.png", "logo.png", "item-atlas.png",
    "master-atlas.png", "menu-atlas.png", "arrow-up.png", "arrow-down.png",
)


def main() -> None:
    system = Path(os.environ["SystemRoot"])
    environment = os.environ.copy()
    environment["PATH"] = os.pathsep.join(map(str, (Path(sys.executable).parent, system / "System32", system)))
    environment["PYINSTALLER_CONFIG_DIR"] = str(ROOT / "build/pyinstaller-cache")
    for key in ("PYTHONHOME", "PYTHONPATH", "QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH", "QML2_IMPORT_PATH"):
        environment.pop(key, None)
    arguments = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--onedir", "--windowed",
        "--name", NAME, "--specpath", str(ROOT / "build"),
        "--workpath", str(ROOT / "build/preview-pyinstaller"), "--distpath", str(ROOT / "dist"),
    ]
    for name in ART:
        path = ROOT / "assets" / name
        if path.is_file():
            arguments += ["--add-data", f"{path};assets"]
    subprocess.run([*arguments, str(ROOT / "app.py")], cwd=ROOT, env=environment, check=True)


if __name__ == "__main__":
    main()
