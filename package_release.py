"""Create a single versioned Windows ZIP and its SHA-256 manifest."""

import argparse
from hashlib import file_digest
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile

from build_preview import ART, NAME, ROOT
from version import VERSION


README_SCREENSHOTS = (Path("docs/editor.png"), Path("docs/editor-ru.png"))


def archive_name(*, without_assets: bool, onefile: bool) -> str:
    suffix = ("-portable" if without_assets else "") + ("-onefile" if onefile else "")
    return f"Cold-Steel-I-Inventory-Editor-v{VERSION}-windows-x64{suffix}.zip"


def package(without_assets: bool, tag: str | None, *, onefile: bool = False) -> tuple[Path, Path]:
    if tag is not None and tag != f"v{VERSION}":
        raise ValueError(f"Release tag {tag} does not match application version {VERSION}.")
    bundle = ROOT / "dist" / ("onefile" if onefile else NAME)
    executable = bundle / f"{NAME}.exe"
    if not executable.is_file():
        raise FileNotFoundError("Build the Windows application before packaging it.")

    if onefile:
        _, members = read_embedded_archive(executable)
        asset_names = {name.removeprefix("assets/") for name in members if name.startswith("assets/")}
        if without_assets and asset_names:
            raise ValueError("The asset-free archive cannot contain the local assets directory.")
        if not without_assets and not set(ART) <= asset_names:
            raise FileNotFoundError("The executable is missing bundled resources.")
        output = ROOT / "release" / ("onefile-portable" if without_assets else "onefile")
        output.mkdir(parents=True, exist_ok=True)
        archive = output / archive_name(without_assets=without_assets, onefile=True)
        with ZipFile(archive, "w", compression=ZIP_DEFLATED, compresslevel=6) as release:
            release.write(executable, executable.name)
        return archive, write_manifest(archive)

    assets = bundle / "_internal/assets"
    if without_assets:
        if assets.exists():
            raise ValueError("The asset-free archive cannot contain the local assets directory.")
    else:
        missing = [name for name in ART if not (assets / name).is_file()]
        if missing:
            raise FileNotFoundError(f"Bundled resources missing: {', '.join(missing)}")

    output = ROOT / "release" / ("portable" if without_assets else "local")
    output.mkdir(parents=True, exist_ok=True)
    archive = output / archive_name(without_assets=without_assets, onefile=False)
    with TemporaryDirectory(prefix="cs1-release-") as directory:
        staged = Path(directory) / NAME
        shutil.copytree(bundle, staged)
        # Frozen Python accepts an unpacked directory at this sys.path entry.
        library = staged / "_internal/base_library.zip"
        with ZipFile(library) as compressed:
            compressed.extractall(library.with_suffix(".unpacked"))
        library.unlink()
        library.with_suffix(".unpacked").rename(library)
        for name in ("README.md", "LICENSE", "CHANGELOG.md"):
            shutil.copyfile(ROOT / name, staged / name)
        for screenshot in README_SCREENSHOTS:
            destination = staged / screenshot
            destination.parent.mkdir(exist_ok=True)
            shutil.copyfile(ROOT / screenshot, destination)
        notices = staged / "third_party"
        shutil.copytree(ROOT / "third_party", notices)
        shutil.copyfile(Path(sys.base_prefix) / "LICENSE.txt", notices / "Python-LICENSE.txt")
        with ZipFile(archive, "w", compression=ZIP_DEFLATED, compresslevel=6) as release:
            for path in sorted(staged.rglob("*")):
                if path.is_file():
                    if path.suffix.lower() in {".dat", ".bak", ".log", ".vdf", ".zip"}:
                        raise ValueError(f"Unexpected file in release: {path.relative_to(staged)}")
                    release.write(path, path.relative_to(staged.parent))
    return archive, write_manifest(archive)


def read_embedded_archive(executable: Path):
    from PyInstaller.archive.readers import CArchiveReader

    embedded = CArchiveReader(str(executable))
    members = {name.replace("\\", "/"): name for name in embedded.toc}
    return embedded, members


def write_manifest(archive: Path) -> Path:
    manifest = archive.with_name("SHA256SUMS.txt")
    with archive.open("rb") as stream:
        digest = file_digest(stream, "sha256").hexdigest()
    manifest.write_text(f"{digest}  {archive.name}\n", encoding="ascii")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--without-assets", action="store_true")
    parser.add_argument("--tag")
    parser.add_argument("--onefile", action="store_true", help="Archive only the single-file executable")
    args = parser.parse_args()
    for path in package(args.without_assets, args.tag, onefile=args.onefile):
        print(path)
