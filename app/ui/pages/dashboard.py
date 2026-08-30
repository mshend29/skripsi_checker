from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QVBoxLayout, QWidget
from sqlalchemy import func, select

from app.database import SessionLocal
from app.models import ReviewComment, Student, Thesis, ThesisDocument


class DashboardPage(QWidget):
    def __init__(self):
        super().__init__()

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(32, 32, 32, 32)
        self.layout.setSpacing(20)

        title = QLabel("Dashboard")
        title.setStyleSheet("font-size: 26px; font-weight: 700;")
        self.layout.addWidget(title)

        subtitle = QLabel(
            "Ringkasan data lokal Skripsi Checker. Semua data tersimpan di komputer ini."
        )
        subtitle.setStyleSheet("color: #666;")
        self.layout.addWidget(subtitle)

        self.grid = QGridLayout()
        self.grid.setSpacing(16)
        self.layout.addLayout(self.grid)
        self.layout.addStretch()

        self.cards: dict[str, QLabel] = {}
        card_titles = [
            ("students", "Mahasiswa"),
            ("theses", "Skripsi"),
            ("documents", "Dokumen"),
            ("comments", "Catatan Koreksi"),
        ]

        for index, (key, label) in enumerate(card_titles):
            card = QFrame()
            card.setFrameShape(QFrame.StyledPanel)
            card.setStyleSheet(
                "QFrame { border: 1px solid #dedede; border-radius: 10px; }"
                "QLabel { border: none; }"
            )
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(18, 16, 18, 16)

            name_label = QLabel(label)
            name_label.setStyleSheet("color: #666; font-size: 13px;")

            value_label = QLabel("0")
            value_label.setStyleSheet("font-size: 28px; font-weight: 700;")

            card_layout.addWidget(name_label)
            card_layout.addWidget(value_label)

            self.cards[key] = value_label
            self.grid.addWidget(card, index // 2, index % 2)

    def refresh(self) -> None:
        with SessionLocal() as session:
            values = {
                "students": session.scalar(select(func.count(Student.id))) or 0,
                "theses": session.scalar(select(func.count(Thesis.id))) or 0,
                "documents": session.scalar(select(func.count(ThesisDocument.id))) or 0,
                "comments": session.scalar(select(func.count(ReviewComment.id))) or 0,
            }

        for key, value in values.items():
            self.cards[key].setText(str(value))
