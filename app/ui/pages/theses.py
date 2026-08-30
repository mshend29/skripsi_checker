from pathlib import Path

from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
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
from sqlalchemy.orm import selectinload

from app.database import SessionLocal
from app.models import Student, Thesis, ThesisDocument
from app.services.document_service import import_proposal


class ThesisDialog(QDialog):
    def __init__(self, students: list[Student], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Tambah Skripsi")
        self.setMinimumWidth(480)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.student = QComboBox()
        for item in students:
            self.student.addItem(f"{item.nim} - {item.name}", item.id)

        self.title = QLineEdit()
        self.title.setPlaceholderText("Boleh dikosongkan jika akan dibaca dari proposal")

        form.addRow("Mahasiswa *", self.student)
        form.addRow("Judul", self.title)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class ThesesPage(QWidget):
    def __init__(self):
        super().__init__()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(16)

        header = QHBoxLayout()
        title_box = QVBoxLayout()

        title = QLabel("Skripsi")
        title.setStyleSheet("font-size: 26px; font-weight: 700;")
        subtitle = QLabel(
            "Kelola proposal, versi dokumen, dan progres skripsi mahasiswa."
        )
        subtitle.setStyleSheet("color: #666;")

        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box)
        header.addStretch()

        import_button = QPushButton("Import Proposal")
        import_button.clicked.connect(self.import_selected_proposal)
        header.addWidget(import_button)

        add_button = QPushButton("+ Tambah Skripsi")
        add_button.clicked.connect(self.add_thesis)
        header.addWidget(add_button)

        layout.addLayout(header)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["ID", "NIM", "Mahasiswa", "Judul", "Status", "Versi Terakhir"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)

        layout.addWidget(self.table)

    def refresh(self) -> None:
        with SessionLocal() as session:
            theses = session.scalars(
                select(Thesis)
                .options(
                    selectinload(Thesis.student),
                    selectinload(Thesis.documents),
                )
                .order_by(Thesis.id.desc())
            ).all()

        self.table.setRowCount(len(theses))
        for row, thesis in enumerate(theses):
            latest_version = max(
                (document.version for document in thesis.documents),
                default=0,
            )
            values = [
                thesis.id,
                thesis.student.nim,
                thesis.student.name,
                thesis.title or "(belum terbaca)",
                thesis.status,
                latest_version or "-",
            ]
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(str(value)))

    def add_thesis(self) -> None:
        with SessionLocal() as session:
            students = session.scalars(
                select(Student).order_by(Student.name.asc())
            ).all()

        if not students:
            QMessageBox.information(
                self,
                "Belum ada mahasiswa",
                "Tambahkan data mahasiswa terlebih dahulu.",
            )
            return

        dialog = ThesisDialog(students, self)
        if dialog.exec() != QDialog.Accepted:
            return

        student_id = dialog.student.currentData()
        title = dialog.title.text().strip()

        with SessionLocal() as session:
            session.add(
                Thesis(
                    student_id=student_id,
                    title=title,
                    status="Proposal",
                )
            )
            session.commit()

        self.refresh()

    def selected_thesis_id(self) -> int | None:
        selected = self.table.selectionModel().selectedRows()
        if not selected:
            return None

        row = selected[0].row()
        item = self.table.item(row, 0)
        return int(item.text()) if item else None

    def import_selected_proposal(self) -> None:
        thesis_id = self.selected_thesis_id()
        if thesis_id is None:
            QMessageBox.information(
                self,
                "Pilih skripsi",
                "Pilih satu data skripsi sebelum mengimpor proposal.",
            )
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Pilih Proposal",
            "",
            "Dokumen Proposal (*.docx *.pdf)",
        )
        if not file_path:
            return

        try:
            with SessionLocal() as session:
                thesis = session.scalar(
                    select(Thesis)
                    .options(selectinload(Thesis.documents))
                    .where(Thesis.id == thesis_id)
                )
                if thesis is None:
                    raise ValueError("Data skripsi tidak ditemukan.")

                version = max(
                    (document.version for document in thesis.documents),
                    default=0,
                ) + 1

                stored_path, detected_title = import_proposal(
                    thesis_id=thesis.id,
                    source_path=Path(file_path),
                    version=version,
                )

                session.add(
                    ThesisDocument(
                        thesis_id=thesis.id,
                        version=version,
                        kind="proposal",
                        file_path=stored_path,
                    )
                )

                if detected_title and not thesis.title.strip():
                    thesis.title = detected_title

                session.commit()

        except Exception as exc:
            QMessageBox.critical(
                self,
                "Import gagal",
                f"Proposal tidak dapat diimpor.\n\n{exc}",
            )
            return

        QMessageBox.information(
            self,
            "Import berhasil",
            f"Proposal tersimpan sebagai versi {version}.",
        )
        self.refresh()
