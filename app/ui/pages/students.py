from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.database import SessionLocal
from app.models import Student


class StudentDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Tambah Mahasiswa")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.nim = QLineEdit()
        self.name = QLineEdit()
        self.email = QLineEdit()
        self.study_program = QLineEdit()
        self.cohort = QLineEdit()

        form.addRow("NIM *", self.nim)
        form.addRow("Nama *", self.name)
        form.addRow("Email", self.email)
        form.addRow("Program Studi", self.study_program)
        form.addRow("Angkatan", self.cohort)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def payload(self) -> dict:
        return {
            "nim": self.nim.text().strip(),
            "name": self.name.text().strip(),
            "email": self.email.text().strip() or None,
            "study_program": self.study_program.text().strip() or None,
            "cohort": self.cohort.text().strip() or None,
        }


class StudentsPage(QWidget):
    def __init__(self):
        super().__init__()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(16)

        header = QHBoxLayout()
        title_box = QVBoxLayout()

        title = QLabel("Mahasiswa")
        title.setStyleSheet("font-size: 26px; font-weight: 700;")
        subtitle = QLabel("Kelola data mahasiswa bimbingan secara offline.")
        subtitle.setStyleSheet("color: #666;")

        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box)
        header.addStretch()

        add_button = QPushButton("+ Tambah Mahasiswa")
        add_button.clicked.connect(self.add_student)
        header.addWidget(add_button)

        layout.addLayout(header)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["ID", "NIM", "Nama", "Email", "Program Studi", "Angkatan"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)

        layout.addWidget(self.table)

    def refresh(self) -> None:
        with SessionLocal() as session:
            students = session.scalars(
                select(Student).order_by(Student.name.asc())
            ).all()

        self.table.setRowCount(len(students))
        for row, student in enumerate(students):
            values = [
                student.id,
                student.nim,
                student.name,
                student.email or "",
                student.study_program or "",
                student.cohort or "",
            ]
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(str(value)))

    def add_student(self) -> None:
        dialog = StudentDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return

        payload = dialog.payload()
        if not payload["nim"] or not payload["name"]:
            QMessageBox.warning(self, "Data belum lengkap", "NIM dan nama wajib diisi.")
            return

        try:
            with SessionLocal() as session:
                session.add(Student(**payload))
                session.commit()
        except IntegrityError:
            QMessageBox.warning(
                self,
                "NIM sudah digunakan",
                "Mahasiswa dengan NIM tersebut sudah ada.",
            )
            return

        self.refresh()
