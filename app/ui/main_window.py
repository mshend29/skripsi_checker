from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.ui.pages.dashboard import DashboardPage
from app.ui.pages.review import ReviewPage
from app.ui.pages.students import StudentsPage
from app.ui.pages.theses import ThesesPage


class PlaceholderPage(QWidget):
    def __init__(self, title: str, description: str):
        super().__init__()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(10)

        heading = QLabel(title)
        heading.setStyleSheet("font-size: 26px; font-weight: 700;")

        info = QLabel(description)
        info.setWordWrap(True)
        info.setStyleSheet("font-size: 14px; color: #666;")

        layout.addWidget(heading)
        layout.addWidget(info)
        layout.addStretch()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Skripsi Checker")
        self.resize(1280, 760)

        root = QWidget()
        self.setCentralWidget(root)

        main_layout = QHBoxLayout(root)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        sidebar = QFrame()
        sidebar.setFixedWidth(220)
        sidebar.setStyleSheet(
            "QFrame { background: #171717; }"
            "QLabel { color: white; }"
            "QPushButton {"
            " color: #eaeaea;"
            " background: transparent;"
            " border: none;"
            " padding: 12px 16px;"
            " text-align: left;"
            " border-radius: 6px;"
            "}"
            "QPushButton:hover { background: #2c2c2c; }"
            "QPushButton:checked { background: #383838; color: white; }"
        )

        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(14, 20, 14, 20)
        sidebar_layout.setSpacing(6)

        brand = QLabel("SKRIPSI\nCHECKER")
        brand.setStyleSheet("font-size: 18px; font-weight: 800;")
        sidebar_layout.addWidget(brand)
        sidebar_layout.addSpacing(22)

        self.stack = QStackedWidget()

        self.dashboard_page = DashboardPage()
        self.students_page = StudentsPage()
        self.theses_page = ThesesPage()
        self.review_page = ReviewPage()
        self.finalization_page = PlaceholderPage(
            "Finalisasi",
            "Tahap finalisasi akan menangani dokumen akhir, abstrak, keyword, "
            "dan penandaan skripsi selesai.",
        )

        pages = [
            ("Dashboard", self.dashboard_page),
            ("Mahasiswa", self.students_page),
            ("Skripsi", self.theses_page),
            ("Koreksi", self.review_page),
            ("Finalisasi", self.finalization_page),
        ]

        self.nav_buttons: list[QPushButton] = []
        for index, (label, page) in enumerate(pages):
            self.stack.addWidget(page)
            button = QPushButton(label)
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(
                lambda checked=False, i=index: self.set_page(i)
            )
            sidebar_layout.addWidget(button)
            self.nav_buttons.append(button)

        sidebar_layout.addStretch()

        mode = QLabel("Offline • SQLite")
        mode.setStyleSheet("color: #aaa; font-size: 12px;")
        sidebar_layout.addWidget(mode)

        main_layout.addWidget(sidebar)
        main_layout.addWidget(self.stack, 1)

        self.set_page(0)

    def set_page(self, index: int) -> None:
        self.stack.setCurrentIndex(index)

        for i, button in enumerate(self.nav_buttons):
            button.setChecked(i == index)

        page = self.stack.currentWidget()
        refresh = getattr(page, "refresh", None)
        if callable(refresh):
            refresh()
