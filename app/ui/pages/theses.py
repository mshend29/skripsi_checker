from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
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
from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from app.database import SessionLocal
from app.models import Student, Thesis, ThesisDocument
from app.services.document_service import resolve_storage_path, store_document


THESIS_STATUSES = [
    "Proposal",
    "Bimbingan",
    "Revisi",
    "Finalisasi",
    "Selesai",
]

DOCUMENT_KIND_LABELS = {
    "proposal": "Proposal",
    "revision": "Revisi",
    "final": "Final",
}

DOCUMENT_KIND_VALUES = {
    label: value for value, label in DOCUMENT_KIND_LABELS.items()
}


class ThesisDialog(QDialog):
    def __init__(
        self,
        students: list[Student],
        thesis: Thesis | None = None,
        parent=None,
    ):
        super().__init__(parent)

        self.thesis_id = thesis.id if thesis else None
        self.setWindowTitle("Edit Skripsi" if thesis else "Tambah Skripsi")
        self.setMinimumWidth(560)

        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        form = QFormLayout()
        form.setSpacing(10)

        self.student = QComboBox()
        for item in students:
            self.student.addItem(f"{item.nim} - {item.name}", item.id)

        self.title = QLineEdit()
        self.title.setPlaceholderText(
            "Boleh dikosongkan saat awal jika akan dibaca dari proposal"
        )

        self.status = QComboBox()
        self.status.addItems(THESIS_STATUSES)

        if thesis:
            student_index = self.student.findData(thesis.student_id)
            if student_index >= 0:
                self.student.setCurrentIndex(student_index)

            self.title.setText(thesis.title or "")

            status_index = self.status.findText(thesis.status)
            if status_index >= 0:
                self.status.setCurrentIndex(status_index)
        else:
            self.status.setCurrentText("Proposal")

        form.addRow("Mahasiswa *", self.student)
        form.addRow("Judul", self.title)
        form.addRow("Status *", self.status)
        layout.addLayout(form)

        note = QLabel(
            "Judul boleh kosong pada tahap awal. Saat proposal diimpor, "
            "aplikasi akan mencoba membaca judul dari dokumen."
        )
        note.setWordWrap(True)
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
            "student_id": self.student.currentData(),
            "title": self.title.text().strip(),
            "status": self.status.currentText(),
        }


class DocumentImportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Import Dokumen Skripsi")
        self.setMinimumWidth(560)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        form = QFormLayout()

        self.kind = QComboBox()
        self.kind.addItems(["Proposal", "Revisi", "Final"])

        file_row = QHBoxLayout()
        self.file_path = QLineEdit()
        self.file_path.setReadOnly(True)
        self.file_path.setPlaceholderText("Pilih file DOCX atau PDF")

        browse_button = QPushButton("Pilih File")
        browse_button.clicked.connect(self.choose_file)

        file_row.addWidget(self.file_path, 1)
        file_row.addWidget(browse_button)

        form.addRow("Jenis Dokumen *", self.kind)
        form.addRow("File *", file_row)
        layout.addLayout(form)

        note = QLabel(
            "Setiap import otomatis menjadi versi baru. File asli akan disalin "
            "ke storage lokal aplikasi."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #777; font-size: 12px;")
        layout.addWidget(note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def choose_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Pilih Dokumen",
            "",
            "Dokumen Skripsi (*.docx *.pdf)",
        )
        if file_path:
            self.file_path.setText(file_path)

    def payload(self) -> tuple[str, str]:
        return (
            DOCUMENT_KIND_VALUES[self.kind.currentText()],
            self.file_path.text().strip(),
        )


class ThesisDetailDialog(QDialog):
    def __init__(self, thesis_id: int, parent=None):
        super().__init__(parent)

        self.thesis_id = thesis_id
        self.setWindowTitle("Detail Skripsi")
        self.resize(940, 600)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        self.heading = QLabel()
        self.heading.setWordWrap(True)
        self.heading.setStyleSheet("font-size: 22px; font-weight: 700;")
        layout.addWidget(self.heading)

        self.meta = QLabel()
        self.meta.setWordWrap(True)
        self.meta.setStyleSheet("color: #666;")
        layout.addWidget(self.meta)

        version_title = QLabel("Riwayat Dokumen")
        version_title.setStyleSheet("font-size: 16px; font-weight: 700;")
        layout.addWidget(version_title)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Versi", "Jenis", "File", "Tanggal Import", "Lokasi"]
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
            3, QHeaderView.ResizeToContents
        )
        self.table.itemDoubleClicked.connect(lambda _: self.open_selected_document())
        layout.addWidget(self.table, 1)

        actions = QHBoxLayout()
        self.open_button = QPushButton("Buka Dokumen")
        self.open_button.clicked.connect(self.open_selected_document)
        self.open_button.setEnabled(False)

        self.table.itemSelectionChanged.connect(
            lambda: self.open_button.setEnabled(
                bool(self.table.selectionModel().selectedRows())
            )
        )

        close_button = QPushButton("Tutup")
        close_button.clicked.connect(self.accept)

        actions.addWidget(self.open_button)
        actions.addStretch()
        actions.addWidget(close_button)
        layout.addLayout(actions)

        self.refresh()

    def refresh(self) -> None:
        with SessionLocal() as session:
            thesis = session.scalar(
                select(Thesis)
                .options(
                    selectinload(Thesis.student),
                    selectinload(Thesis.documents),
                )
                .where(Thesis.id == self.thesis_id)
            )

            if thesis is None:
                self.heading.setText("Data skripsi tidak ditemukan")
                self.meta.setText("")
                self.table.setRowCount(0)
                return

            self.heading.setText(
                thesis.title or "(Judul belum tersedia)"
            )
            self.meta.setText(
                f"{thesis.student.nim} - {thesis.student.name}  •  "
                f"Status: {thesis.status}  •  "
                f"Mulai: {thesis.started_at.strftime('%d-%m-%Y')}"
            )

            documents = sorted(
                thesis.documents,
                key=lambda item: item.version,
                reverse=True,
            )

        self.table.setRowCount(len(documents))
        for row, document in enumerate(documents):
            resolved_path = resolve_storage_path(document.file_path)
            values = [
                document.version,
                DOCUMENT_KIND_LABELS.get(document.kind, document.kind.title()),
                Path(document.file_path).name,
                document.uploaded_at.strftime("%d-%m-%Y %H:%M"),
                document.file_path,
            ]

            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column == 0:
                    item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, column, item)

            version_item = self.table.item(row, 0)
            version_item.setData(Qt.UserRole, str(resolved_path))

    def open_selected_document(self) -> None:
        selected = self.table.selectionModel().selectedRows()
        if not selected:
            return

        item = self.table.item(selected[0].row(), 0)
        if item is None:
            return

        file_path = Path(item.data(Qt.UserRole))
        if not file_path.exists():
            QMessageBox.warning(
                self,
                "File tidak ditemukan",
                (
                    "File dokumen tidak ditemukan di storage lokal.\n\n"
                    f"{file_path}"
                ),
            )
            return

        opened = QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(file_path.resolve()))
        )
        if not opened:
            QMessageBox.warning(
                self,
                "Dokumen tidak dapat dibuka",
                "Windows tidak menemukan aplikasi untuk membuka file tersebut.",
            )


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
            "Kelola proposal, revisi, versi dokumen, dan progres skripsi mahasiswa."
        )
        subtitle.setStyleSheet("color: #666;")

        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box)
        header.addStretch()

        add_button = QPushButton("+ Tambah Skripsi")
        add_button.clicked.connect(self.add_thesis)
        header.addWidget(add_button)

        layout.addLayout(header)

        filters = QHBoxLayout()
        filters.setSpacing(8)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(
            "Cari NIM, mahasiswa, judul, atau status..."
        )
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self.refresh)
        filters.addWidget(self.search_input, 1)

        self.status_filter = QComboBox()
        self.status_filter.addItem("Semua Status")
        self.status_filter.addItems(THESIS_STATUSES)
        self.status_filter.currentTextChanged.connect(self.refresh)
        filters.addWidget(self.status_filter)

        self.detail_button = QPushButton("Detail")
        self.detail_button.clicked.connect(self.show_detail)
        filters.addWidget(self.detail_button)

        self.edit_button = QPushButton("Edit")
        self.edit_button.clicked.connect(self.edit_selected)
        filters.addWidget(self.edit_button)

        self.import_button = QPushButton("Import Dokumen")
        self.import_button.clicked.connect(self.import_selected_document)
        filters.addWidget(self.import_button)

        self.delete_button = QPushButton("Hapus")
        self.delete_button.clicked.connect(self.delete_selected)
        filters.addWidget(self.delete_button)

        layout.addLayout(filters)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            [
                "ID",
                "NIM",
                "Mahasiswa",
                "Judul",
                "Status",
                "Versi",
                "Dokumen",
            ]
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
            4, QHeaderView.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            5, QHeaderView.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            6, QHeaderView.ResizeToContents
        )
        self.table.itemDoubleClicked.connect(lambda _: self.show_detail())
        self.table.itemSelectionChanged.connect(self.update_action_state)

        layout.addWidget(self.table)

        footer = QHBoxLayout()
        self.count_label = QLabel("0 skripsi")
        self.count_label.setStyleSheet("color: #777; font-size: 12px;")
        footer.addWidget(self.count_label)
        footer.addStretch()
        layout.addLayout(footer)

        self.update_action_state()

    def refresh(self, *_args) -> None:
        keyword = (
            self.search_input.text().strip()
            if hasattr(self, "search_input")
            else ""
        )
        status = (
            self.status_filter.currentText()
            if hasattr(self, "status_filter")
            else "Semua Status"
        )

        query = (
            select(Thesis)
            .join(Thesis.student)
            .options(
                selectinload(Thesis.student),
                selectinload(Thesis.documents),
            )
            .order_by(Thesis.id.desc())
        )

        if keyword:
            pattern = f"%{keyword}%"
            query = query.where(
                or_(
                    Student.nim.ilike(pattern),
                    Student.name.ilike(pattern),
                    Thesis.title.ilike(pattern),
                    Thesis.status.ilike(pattern),
                )
            )

        if status != "Semua Status":
            query = query.where(Thesis.status == status)

        with SessionLocal() as session:
            theses = session.scalars(query).all()

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
                len(thesis.documents),
            ]

            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column in {0, 5, 6}:
                    item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, column, item)

        self.count_label.setText(f"{len(theses)} skripsi")
        self.update_action_state()

    def selected_thesis_id(self) -> int | None:
        selected = self.table.selectionModel().selectedRows()
        if not selected:
            return None

        item = self.table.item(selected[0].row(), 0)
        return int(item.text()) if item else None

    def update_action_state(self) -> None:
        has_selection = self.selected_thesis_id() is not None
        for button in (
            self.detail_button,
            self.edit_button,
            self.import_button,
            self.delete_button,
        ):
            button.setEnabled(has_selection)

    def load_students(self) -> list[Student]:
        with SessionLocal() as session:
            return session.scalars(
                select(Student).order_by(Student.name.asc())
            ).all()

    def student_has_other_thesis(
        self,
        student_id: int,
        current_thesis_id: int | None = None,
    ) -> bool:
        query = select(Thesis.id).where(Thesis.student_id == student_id)
        if current_thesis_id is not None:
            query = query.where(Thesis.id != current_thesis_id)

        with SessionLocal() as session:
            return session.scalar(query) is not None

    def add_thesis(self) -> None:
        students = self.load_students()

        if not students:
            QMessageBox.information(
                self,
                "Belum ada mahasiswa",
                "Tambahkan data mahasiswa terlebih dahulu.",
            )
            return

        dialog = ThesisDialog(students=students, parent=self)
        if dialog.exec() != QDialog.Accepted:
            return

        payload = dialog.payload()
        if payload["student_id"] is None:
            QMessageBox.warning(
                self,
                "Mahasiswa belum dipilih",
                "Pilih mahasiswa untuk data skripsi.",
            )
            return

        if self.student_has_other_thesis(payload["student_id"]):
            QMessageBox.warning(
                self,
                "Skripsi sudah tersedia",
                "Mahasiswa tersebut sudah memiliki data skripsi aktif.",
            )
            return

        with SessionLocal() as session:
            session.add(Thesis(**payload))
            session.commit()

        self.refresh()

    def edit_selected(self) -> None:
        thesis_id = self.selected_thesis_id()
        if thesis_id is None:
            return

        students = self.load_students()

        with SessionLocal() as session:
            thesis = session.get(Thesis, thesis_id)
            if thesis is None:
                QMessageBox.warning(
                    self,
                    "Data tidak ditemukan",
                    "Data skripsi sudah tidak tersedia.",
                )
                self.refresh()
                return

            dialog = ThesisDialog(
                students=students,
                thesis=thesis,
                parent=self,
            )

        if dialog.exec() != QDialog.Accepted:
            return

        payload = dialog.payload()

        if self.student_has_other_thesis(
            payload["student_id"],
            current_thesis_id=thesis_id,
        ):
            QMessageBox.warning(
                self,
                "Skripsi sudah tersedia",
                "Mahasiswa tersebut sudah memiliki data skripsi lain.",
            )
            return

        with SessionLocal() as session:
            thesis = session.get(Thesis, thesis_id)
            if thesis is None:
                self.refresh()
                return

            thesis.student_id = payload["student_id"]
            thesis.title = payload["title"]
            thesis.status = payload["status"]

            if payload["status"] == "Selesai":
                thesis.finalized_at = thesis.finalized_at or datetime.now()
            else:
                thesis.finalized_at = None

            session.commit()

        self.refresh()

    def show_detail(self) -> None:
        thesis_id = self.selected_thesis_id()
        if thesis_id is None:
            return

        dialog = ThesisDetailDialog(thesis_id=thesis_id, parent=self)
        dialog.exec()
        self.refresh()

    def import_selected_document(self) -> None:
        thesis_id = self.selected_thesis_id()
        if thesis_id is None:
            return

        dialog = DocumentImportDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return

        kind, file_path = dialog.payload()
        if not file_path:
            QMessageBox.warning(
                self,
                "File belum dipilih",
                "Pilih file DOCX atau PDF yang akan diimpor.",
            )
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

                stored_path, detected_title = store_document(
                    thesis_id=thesis.id,
                    source_path=Path(file_path),
                    version=version,
                    kind=kind,
                )

                session.add(
                    ThesisDocument(
                        thesis_id=thesis.id,
                        version=version,
                        kind=kind,
                        file_path=stored_path,
                    )
                )

                if detected_title and not (thesis.title or "").strip():
                    thesis.title = detected_title

                if kind == "revision" and thesis.status in {
                    "Proposal",
                    "Bimbingan",
                }:
                    thesis.status = "Revisi"
                elif kind == "final" and thesis.status != "Selesai":
                    thesis.status = "Finalisasi"

                session.commit()

        except Exception as exc:
            QMessageBox.critical(
                self,
                "Import gagal",
                f"Dokumen tidak dapat diimpor.\n\n{exc}",
            )
            return

        QMessageBox.information(
            self,
            "Import berhasil",
            (
                f"{DOCUMENT_KIND_LABELS[kind]} tersimpan sebagai versi "
                f"{version}."
            ),
        )
        self.refresh()

    def delete_selected(self) -> None:
        thesis_id = self.selected_thesis_id()
        if thesis_id is None:
            return

        with SessionLocal() as session:
            thesis = session.scalar(
                select(Thesis)
                .options(
                    selectinload(Thesis.student),
                    selectinload(Thesis.documents),
                )
                .where(Thesis.id == thesis_id)
            )
            if thesis is None:
                self.refresh()
                return

            if thesis.documents:
                QMessageBox.warning(
                    self,
                    "Skripsi tidak dapat dihapus",
                    (
                        f"Data skripsi {thesis.student.name} sudah memiliki "
                        f"{len(thesis.documents)} dokumen tersimpan.\n\n"
                        "Penghapusan diblokir agar riwayat proposal/revisi tidak "
                        "hilang. Ubah status menjadi Selesai jika proses bimbingan "
                        "sudah berakhir."
                    ),
                )
                return

            answer = QMessageBox.question(
                self,
                "Hapus skripsi",
                (
                    f"Yakin ingin menghapus data skripsi milik "
                    f"{thesis.student.name}?\n\n"
                    "Tindakan ini tidak dapat dibatalkan."
                ),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return

            session.delete(thesis)
            session.commit()

        self.refresh()
