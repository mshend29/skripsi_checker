import sys

from PySide6.QtWidgets import QApplication

from app.database import init_db
from app.ui.main_window import MainWindow


def main() -> int:
    init_db()

    app = QApplication(sys.argv)
    app.setApplicationName("Skripsi Checker")
    app.setOrganizationName("Skripsi Checker")

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
