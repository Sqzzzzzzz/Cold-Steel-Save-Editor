"""Check the shipped ZIP, then start its extracted EXE with a system-only PATH."""

import argparse
from hashlib import file_digest
import os
from pathlib import Path
from struct import pack, unpack_from
import subprocess
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from build_preview import ART, NAME, ROOT
from package_release import README_SCREENSHOTS
from qt_backend import ITEM_TABLE
from test_cs1 import make_save
from version import VERSION


def verify(directory: Path, *, full_theme: bool, save: Path | None) -> None:
    suffix = "" if full_theme else "-portable"
    archive = directory / f"Cold-Steel-I-Inventory-Editor-v{VERSION}-windows-x64{suffix}.zip"
    expected, filename = (directory / "SHA256SUMS.txt").read_text(encoding="ascii").strip().split("  ", 1)
    with archive.open("rb") as stream:
        if filename != archive.name or file_digest(stream, "sha256").hexdigest() != expected:
            raise ValueError("Release archive checksum mismatch.")
    with TemporaryDirectory(prefix="cs1-package-test-") as temporary:
        root = Path(temporary)
        with ZipFile(archive) as files:
            if any(Path(member).suffix.lower() in {".zip", ".dat", ".bak", ".log"} for member in files.namelist()):
                raise ValueError("Unexpected nested archive or test data in release.")
            files.extractall(root)
        bundle = root / NAME
        for screenshot in README_SCREENSHOTS:
            if (bundle / screenshot).read_bytes() != (ROOT / screenshot).read_bytes():
                raise ValueError(f"Bundled screenshot differs from the release source: {screenshot}")
        exe = bundle / f"{NAME}.exe"
        binary = exe.read_bytes()
        pe = unpack_from("<I", binary, 0x3C)[0]
        if (binary[:2] != b"MZ" or binary[pe:pe + 4] != b"PE\0\0"
                or unpack_from("<H", binary, pe + 4)[0] != 0x8664
                or unpack_from("<H", binary, pe + 24 + 68)[0] != 2):
            raise ValueError("Expected a Windows x64 executable with the GUI subsystem.")
        if not (bundle / "_internal/PySide6/translations/qtbase_ru.qm").is_file():
            raise FileNotFoundError("The Qt Russian translation is missing.")
        assets = bundle / "_internal/assets"
        if full_theme and any(not (assets / name).is_file() for name in ART):
            raise FileNotFoundError("The themed package is incomplete.")
        if full_theme:
            for name in ART:
                if (assets / name).read_bytes() != (Path(__file__).resolve().parent / "assets" / name).read_bytes():
                    raise ValueError(f"Bundled asset differs from the release source: {name}")
        if not full_theme and assets.exists():
            raise ValueError("The portable package contains local assets.")
        system = Path(os.environ["SystemRoot"])
        environment = {key: value for key, value in os.environ.items()
                       if not key.upper().startswith(("PYTHON", "QT_"))}
        environment["PATH"] = os.pathsep.join(map(str, (system / "System32", system)))
        subprocess.run([str(exe), "--smoke-test-clean"], cwd=bundle, env=environment, timeout=25, check=True)
        if full_theme:
            copy = root / "test-slot.dat"
            args = ["--save", str(copy)]
            if save is None:
                game = root / "game-fixture"
                table = game / ITEM_TABLE
                table.parent.mkdir(parents=True)
                metadata = bytearray(46)
                metadata[0], metadata[39] = 0x81, 99
                table.write_bytes(pack("<H", 1) + b"item\0\0\0" + bytes(4) + b"SL\0" + metadata
                                  + b"Sample Recovery Item\0Restores health\0")
                snapshot = make_save((0, 2))
                args += ["--game", str(game)]
            else:
                snapshot = save.read_bytes()
            copy.write_bytes(snapshot)
            subprocess.run([str(exe), "--smoke-test", *args], cwd=bundle, env=environment, timeout=25, check=True)
            if copy.read_bytes() != snapshot or (save is not None and save.read_bytes() != snapshot):
                raise ValueError("A smoke test changed the save or its copy.")
    print(f"Verified archive, checksum and startup: {archive.name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--full-theme", action="store_true")
    parser.add_argument("--save", type=Path)
    args = parser.parse_args()
    verify(args.directory, full_theme=args.full_theme, save=args.save)
