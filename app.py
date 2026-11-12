"""Launch the local Cold Steel I interface preview."""

import argparse
from pathlib import Path
import sys

from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from qt_backend import EditorCore
from qt_window import APP_NAME, VERSION, MainWindow


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", type=Path, help="Cold Steel I installation directory")
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
    window = MainWindow(EditorCore(args.game))
    screen = app.primaryScreen()
    if screen is not None:
        available = screen.availableGeometry()
        window.resize(
            min(window.width(), max(window.minimumWidth(), available.width())),
            min(window.height(), max(window.minimumHeight(), available.height())),
        )
    window.show()

    if args.smoke_test:
        poll = QTimer(window)

        def check_window():
            if window.core.save is None or window.scan_thread is not None:
                return
            window.navigate_section("catalog")
            ready = (
                window.isVisible() and window.cat_table.rowCount() > 0
                and not window.centralWidget().wall.isNull()
                and not window.header.academy.isNull()
                and not window._icon(0, window.core.catalog.get(0, {})).isNull()
                and window.core.storage is None
            )
            app.exit(0 if ready else 2)

        poll.timeout.connect(check_window)
        poll.start(200)
        QTimer.singleShot(12000, lambda: app.exit(3))
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
