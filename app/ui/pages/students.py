import re

from PySide6.QtCore import Qt
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
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from app.database import SessionLocal
from app.models import Student, Thesis


EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class StudentDialog(QDialog):
    def __init__(self, student: Student | None = None, parent=None):
        super().__init__(parent)

        self.student_id = student.id if student else None
        self.setWindowTitle("Edit Mahasiswa" if student else "Tambah Mahasiswa")
        self.setMinimumWidth(440)

        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        form = QFormLayout()
        form.setSpacing(10)

        self.nim = QLineEdit()
        self.name = QLineEdit()
        self.email = QLineEdit()
        self.study_program = QLineEdit()
        self.cohort = QLineEdit()

        self.nim.setPlaceholderText("Contoh: 22123456")
        self.name.setPlaceholderText("Nama lengkap mahasiswa")
        self.email.setPlaceholderText("nama@email.com")
        self.study_program.setPlaceholderText("Contoh: Manajemen")
        self.cohort.setPlaceholderText("Contoh: 2022")

        if student:
            self.nim.setText(student.nim)
            self.name.setText(student.name)
            self.email.setText(student.email or "")
            self.study_program.setText(student.study_program or "")
            self.cohort.setText(student.cohort or "")

        form.addRow("NIM *", self.nim)
        form.addRow("Nama *", self.name)
        form.addRow("Email", self.email)
        form.addRow("Program Studi", self.study_program)
        form.addRow("Angkatan", self.cohort)
        layout.addLayout(form)

        note = QLabel("* Wajib diisi")
        note.setStyleSheet("color: #777; font-size: 12px;")
        layout.addWidget(note)

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
        subtitle = QLabel(
            "Kelola data mahasiswa bimbingan. Data tersimpan secara lokal."
        )
        subtitle.setStyleSheet("color: #666;")

        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box)
        header.addStretch()

        add_button = QPushButton("+ Tambah Mahasiswa")
        add_button.clicked.connect(self.add_student)
        header.addWidget(add_button)

        layout.addLayout(header)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(
            "Cari NIM, nama, email, program studi, atau angkatan..."
        )
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self.refresh)
        toolbar.addWidget(self.search_input, 1)

        self.edit_button = QPushButton("Edit")
        self.edit_button.clicked.connect(self.edit_selected)
        toolbar.addWidget(self.edit_button)

        self.delete_button = QPushButton("Hapus")
        self.delete_button.clicked.connect(self.delete_selected)
        toolbar.addWidget(self.delete_button)

        layout.addLayout(toolbar)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["ID", "NIM", "Nama", "Email", "Program Studi", "Angkatan"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            5, QHeaderView.ResizeToContents
        )
        self.table.itemDoubleClicked.connect(lambda _: self.edit_selected())
        self.table.itemSelectionChanged.connect(self.update_action_state)

        layout.addWidget(self.table)

        footer = QHBoxLayout()
        self.count_label = QLabel("0 mahasiswa")
        self.count_label.setStyleSheet("color: #777; font-size: 12px;")
        footer.addWidget(self.count_label)
        footer.addStretch()
        layout.addLayout(footer)

        self.update_action_state()

    def refresh(self, *_args) -> None:
        keyword = self.search_input.text().strip() if hasattr(self, "search_input") else ""

        query = select(Student).order_by(Student.name.asc())
        if keyword:
            pattern = f"%{keyword}%"
            query = query.where(
                or_(
                    Student.nim.ilike(pattern),
                    Student.name.ilike(pattern),
                    Student.email.ilike(pattern),
                    Student.study_program.ilike(pattern),
                    Student.cohort.ilike(pattern),
                )
            )

        with SessionLocal() as session:
            students = session.scalars(query).all()

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
                item = QTableWidgetItem(str(value))
                if column == 0:
                    item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, column, item)

        suffix = "hasil" if keyword else "mahasiswa"
        self.count_label.setText(f"{len(students)} {suffix}")
        self.update_action_state()

    def selected_student_id(self) -> int | None:
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            return None

        item = self.table.item(selected_rows[0].row(), 0)
        return int(item.text()) if item else None

    def update_action_state(self) -> None:
        has_selection = self.selected_student_id() is not None
        self.edit_button.setEnabled(has_selection)
        self.delete_button.setEnabled(has_selection)

    def validate_payload(self, payload: dict) -> str | None:
        if not payload["nim"]:
            return "NIM wajib diisi."

        if not payload["name"]:
            return "Nama mahasiswa wajib diisi."

        if payload["email"] and not EMAIL_PATTERN.match(payload["email"]):
            return "Format email belum valid."

        cohort = payload["cohort"]
        if cohort and (not cohort.isdigit() or len(cohort) != 4):
            return "Angkatan harus berupa 4 digit tahun, contoh: 2022."

        return None

    def add_student(self) -> None:
        dialog = StudentDialog(parent=self)
        if dialog.exec() != QDialog.Accepted:
            return

        payload = dialog.payload()
        error = self.validate_payload(payload)
        if error:
            QMessageBox.warning(self, "Data belum valid", error)
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

    def edit_selected(self) -> None:
        student_id = self.selected_student_id()
        if student_id is None:
            return

        with SessionLocal() as session:
            student = session.get(Student, student_id)
            if student is None:
                QMessageBox.warning(
                    self,
                    "Data tidak ditemukan",
                    "Data mahasiswa sudah tidak tersedia.",
                )
                self.refresh()
                return

            dialog = StudentDialog(student=student, parent=self)

        if dialog.exec() != QDialog.Accepted:
            return

        payload = dialog.payload()
        error = self.validate_payload(payload)
        if error:
            QMessageBox.warning(self, "Data belum valid", error)
            return

        try:
            with SessionLocal() as session:
                student = session.get(Student, student_id)
                if student is None:
                    QMessageBox.warning(
                        self,
                        "Data tidak ditemukan",
                        "Data mahasiswa sudah tidak tersedia.",
                    )
                    self.refresh()
                    return

                student.nim = payload["nim"]
                student.name = payload["name"]
                student.email = payload["email"]
                student.study_program = payload["study_program"]
                student.cohort = payload["cohort"]
                session.commit()
        except IntegrityError:
            QMessageBox.warning(
                self,
                "NIM sudah digunakan",
                "NIM tersebut digunakan oleh mahasiswa lain.",
            )
            return

        self.refresh()

    def delete_selected(self) -> None:
        student_id = self.selected_student_id()
        if student_id is None:
            return

        with SessionLocal() as session:
            student = session.get(Student, student_id)
            if student is None:
                self.refresh()
                return

            thesis_count = session.scalar(
                select(func.count(Thesis.id)).where(Thesis.student_id == student_id)
            ) or 0

            if thesis_count:
                QMessageBox.warning(
                    self,
                    "Mahasiswa tidak dapat dihapus",
                    (
                        f"{student.name} sudah memiliki {thesis_count} data skripsi.\n\n"
                        "Hapus atau pindahkan data skripsinya terlebih dahulu agar "
                        "riwayat dokumen tidak ikut hilang."
                    ),
                )
                return

            answer = QMessageBox.question(
                self,
                "Hapus mahasiswa",
                (
                    f"Yakin ingin menghapus data mahasiswa berikut?\n\n"
                    f"{student.nim} - {student.name}\n\n"
                    "Tindakan ini tidak dapat dibatalkan."
                ),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return

            session.delete(student)
            session.commit()

        self.refresh()
