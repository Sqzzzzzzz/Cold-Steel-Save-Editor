"""Launch the Cold Steel I Steam inventory editor."""

import argparse
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

from PySide6.QtCore import QSettings, QTimer
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from qt_backend import EditorCore
from qt_window import APP_NAME, VERSION, MainWindow
from save_storage import SteamSaveStorage


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", type=Path, help="Cold Steel I installation directory")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--save", type=Path, help="Open a Cold Steel I save file")
    mode.add_argument("--demo", action="store_true", help="Use the sample inventory")
    parser.add_argument("--smoke-test", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(VERSION)
    app.setStyle("Fusion")
    palette = app.palette()
    for role in (QPalette.ColorRole.ButtonText, QPalette.ColorRole.Text, QPalette.ColorRole.WindowText):
        palette.setColor(role, QColor("#f2e9e8"))
    app.setPalette(palette)
    temporary = TemporaryDirectory(prefix="cs1-smoke-") if args.smoke_test else None
    profile = (
        QSettings(str(Path(temporary.name) / "profile.ini"), QSettings.Format.IniFormat)
        if temporary else None
    )
    window = MainWindow(EditorCore(args.game, profile=profile, storage=None if args.demo else SteamSaveStorage()))
    screen = app.primaryScreen()
    if screen is not None:
        available = screen.availableGeometry()
        window.resize(
            min(window.width(), max(window.minimumWidth(), available.width())),
            min(window.height(), max(window.minimumHeight(), available.height())),
        )
    window.show()
    if args.save:
        QTimer.singleShot(0, lambda: window.open_save(args.save))

    if args.smoke_test:
        poll = QTimer(window)

        def check_window():
            if not window.core.catalog or window.scan_thread is not None or (args.save and window.core.source is None):
                return
            window.navigate_section("catalog")
            ready = (
                window.isVisible() and window.cat_table.rowCount() > 0
                and not window.centralWidget().wall.isNull()
                and not window.header.academy.isNull()
                and not window._icon(0, window.core.catalog.get(0, {})).isNull()
                and (args.save is None or window.core.source == args.save.resolve())
            )
            app.exit(0 if ready else 2)

        poll.timeout.connect(check_window)
        poll.start(200)
        QTimer.singleShot(12000, lambda: app.exit(3))
    try:
        return app.exec()
    finally:
        if temporary:
            temporary.cleanup()


if __name__ == "__main__":
    sys.exit(main())
