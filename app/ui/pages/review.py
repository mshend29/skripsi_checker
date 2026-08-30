from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QTextCursor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import SessionLocal
from app.models import ReviewComment, Thesis, ThesisDocument
from app.services.document_service import (
    extract_sections,
    extract_text,
    resolve_storage_path,
)


DOCUMENT_KIND_LABELS = {
    "proposal": "Proposal",
    "revision": "Revisi",
    "final": "Final",
}

COMMENT_STATUS_LABELS = {
    "Open": "Terbuka",
    "Resolved": "Selesai",
}


class CommentDialog(QDialog):
    def __init__(
        self,
        sections: list[str],
        comment: ReviewComment | None = None,
        selected_section: str | None = None,
        parent=None,
    ):
        super().__init__(parent)

        self.setWindowTitle("Edit Komentar" if comment else "Tambah Komentar")
        self.resize(560, 360)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        form = QFormLayout()

        self.section = QComboBox()
        self.section.setEditable(True)
        self.section.addItem("Umum")
        self.section.addItems(sections)

        initial_section = (
            comment.section
            if comment and comment.section
            else selected_section or "Umum"
        )
        index = self.section.findText(initial_section)
        if index >= 0:
            self.section.setCurrentIndex(index)
        else:
            self.section.setCurrentText(initial_section)

        form.addRow("Bagian", self.section)
        layout.addLayout(form)

        self.content = QPlainTextEdit()
        self.content.setPlaceholderText(
            "Tuliskan catatan, koreksi, atau arahan revisi untuk mahasiswa..."
        )
        if comment:
            self.content.setPlainText(comment.content)

        layout.addWidget(self.content, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def validate_and_accept(self) -> None:
        if not self.content.toPlainText().strip():
            QMessageBox.warning(
                self,
                "Komentar kosong",
                "Isi komentar terlebih dahulu.",
            )
            return

        self.accept()

    def payload(self) -> dict:
        section = self.section.currentText().strip() or "Umum"
        return {
            "section": section,
            "content": self.content.toPlainText().strip(),
        }


class ReviewPage(QWidget):
    def __init__(self):
        super().__init__()

        self.current_document_id: int | None = None
        self.current_sections: list[str] = []
        self.current_file_path: Path | None = None
        self._loading = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        title = QLabel("Koreksi Skripsi")
        title.setStyleSheet("font-size: 26px; font-weight: 700;")
        layout.addWidget(title)

        subtitle = QLabel(
            "Catatan koreksi tersimpan pada versi dokumen yang sedang dibuka, "
            "sehingga riwayat komentar antar-versi tetap terpisah."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #666;")
        layout.addWidget(subtitle)

        selectors = QHBoxLayout()
        selectors.setSpacing(8)

        selectors.addWidget(QLabel("Skripsi"))
        self.thesis_combo = QComboBox()
        self.thesis_combo.setMinimumWidth(320)
        self.thesis_combo.currentIndexChanged.connect(self.load_documents)
        selectors.addWidget(self.thesis_combo, 2)

        selectors.addWidget(QLabel("Versi"))
        self.document_combo = QComboBox()
        self.document_combo.setMinimumWidth(220)
        self.document_combo.currentIndexChanged.connect(self.load_document)
        selectors.addWidget(self.document_combo, 1)

        self.open_file_button = QPushButton("Buka File Asli")
        self.open_file_button.clicked.connect(self.open_original_file)
        selectors.addWidget(self.open_file_button)

        layout.addLayout(selectors)

        splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(splitter, 1)

        document_panel = QWidget()
        document_layout = QVBoxLayout(document_panel)
        document_layout.setContentsMargins(0, 0, 8, 0)
        document_layout.setSpacing(8)

        navigation = QHBoxLayout()
        navigation.addWidget(QLabel("Bagian"))

        self.section_combo = QComboBox()
        self.section_combo.currentTextChanged.connect(self.jump_to_section)
        navigation.addWidget(self.section_combo, 1)

        document_layout.addLayout(navigation)

        self.document_info = QLabel("Belum ada dokumen dipilih.")
        self.document_info.setWordWrap(True)
        self.document_info.setStyleSheet("color: #777; font-size: 12px;")
        document_layout.addWidget(self.document_info)

        self.document_view = QTextEdit()
        self.document_view.setReadOnly(True)
        self.document_view.setPlaceholderText(
            "Isi dokumen DOCX/PDF akan ditampilkan di sini."
        )
        document_layout.addWidget(self.document_view, 1)

        splitter.addWidget(document_panel)

        comments_panel = QWidget()
        comments_layout = QVBoxLayout(comments_panel)
        comments_layout.setContentsMargins(8, 0, 0, 0)
        comments_layout.setSpacing(8)

        comments_header = QHBoxLayout()

        comments_title = QLabel("Catatan Dosen")
        comments_title.setStyleSheet("font-size: 16px; font-weight: 700;")
        comments_header.addWidget(comments_title)
        comments_header.addStretch()

        self.comment_filter = QComboBox()
        self.comment_filter.addItems(["Semua", "Terbuka", "Selesai"])
        self.comment_filter.currentTextChanged.connect(self.load_comments)
        comments_header.addWidget(self.comment_filter)

        comments_layout.addLayout(comments_header)

        self.comments_table = QTableWidget(0, 4)
        self.comments_table.setHorizontalHeaderLabels(
            ["Bagian", "Komentar", "Status", "Tanggal"]
        )
        self.comments_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.comments_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.comments_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.comments_table.setAlternatingRowColors(True)
        self.comments_table.verticalHeader().setVisible(False)
        self.comments_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch
        )
        self.comments_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeToContents
        )
        self.comments_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeToContents
        )
        self.comments_table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeToContents
        )
        self.comments_table.itemDoubleClicked.connect(
            lambda _: self.edit_selected_comment()
        )
        self.comments_table.itemSelectionChanged.connect(
            self.update_comment_actions
        )
        comments_layout.addWidget(self.comments_table, 1)

        self.comment_count_label = QLabel("0 komentar")
        self.comment_count_label.setStyleSheet("color: #777; font-size: 12px;")
        comments_layout.addWidget(self.comment_count_label)

        actions = QHBoxLayout()

        self.add_comment_button = QPushButton("+ Tambah Komentar")
        self.add_comment_button.clicked.connect(self.add_comment)
        actions.addWidget(self.add_comment_button)

        self.edit_comment_button = QPushButton("Edit")
        self.edit_comment_button.clicked.connect(self.edit_selected_comment)
        actions.addWidget(self.edit_comment_button)

        self.toggle_status_button = QPushButton("Tandai Selesai")
        self.toggle_status_button.clicked.connect(self.toggle_selected_status)
        actions.addWidget(self.toggle_status_button)

        self.delete_comment_button = QPushButton("Hapus")
        self.delete_comment_button.clicked.connect(self.delete_selected_comment)
        actions.addWidget(self.delete_comment_button)

        comments_layout.addLayout(actions)

        splitter.addWidget(comments_panel)
        splitter.setSizes([700, 500])

        self.update_document_actions()
        self.update_comment_actions()

    def refresh(self) -> None:
        selected_thesis_id = self.thesis_combo.currentData()

        with SessionLocal() as session:
            theses = session.scalars(
                select(Thesis)
                .options(
                    selectinload(Thesis.student),
                    selectinload(Thesis.documents),
                )
                .order_by(Thesis.student_id.asc())
            ).all()

        self._loading = True
        self.thesis_combo.clear()

        for thesis in theses:
            document_count = len(thesis.documents)
            label = (
                f"{thesis.student.nim} - {thesis.student.name}"
                f"  ({document_count} dokumen)"
            )
            self.thesis_combo.addItem(label, thesis.id)

        if selected_thesis_id is not None:
            index = self.thesis_combo.findData(selected_thesis_id)
            if index >= 0:
                self.thesis_combo.setCurrentIndex(index)

        self._loading = False
        self.load_documents()

    def load_documents(self, *_args) -> None:
        if self._loading:
            return

        thesis_id = self.thesis_combo.currentData()

        self._loading = True
        self.document_combo.clear()

        if thesis_id is not None:
            with SessionLocal() as session:
                thesis = session.scalar(
                    select(Thesis)
                    .options(selectinload(Thesis.documents))
                    .where(Thesis.id == thesis_id)
                )

                documents = (
                    sorted(
                        thesis.documents,
                        key=lambda item: item.version,
                        reverse=True,
                    )
                    if thesis
                    else []
                )

            for document in documents:
                kind = DOCUMENT_KIND_LABELS.get(
                    document.kind,
                    document.kind.title(),
                )
                label = f"V{document.version} - {kind}"
                self.document_combo.addItem(label, document.id)

        self._loading = False
        self.load_document()

    def load_document(self, *_args) -> None:
        if self._loading:
            return

        document_id = self.document_combo.currentData()
        self.current_document_id = document_id
        self.current_sections = []
        self.current_file_path = None

        self.document_view.clear()
        self.section_combo.blockSignals(True)
        self.section_combo.clear()
        self.section_combo.blockSignals(False)

        if document_id is None:
            self.document_info.setText(
                "Skripsi ini belum mempunyai dokumen yang dapat dikoreksi."
            )
            self.load_comments()
            self.update_document_actions()
            return

        try:
            with SessionLocal() as session:
                document = session.scalar(
                    select(ThesisDocument)
                    .options(
                        selectinload(ThesisDocument.thesis).selectinload(
                            Thesis.student
                        )
                    )
                    .where(ThesisDocument.id == document_id)
                )

                if document is None:
                    raise ValueError("Versi dokumen tidak ditemukan.")

                file_path = resolve_storage_path(document.file_path)
                if not file_path.exists():
                    raise FileNotFoundError(str(file_path))

                text = extract_text(file_path)
                sections = extract_sections(text)

                student_name = document.thesis.student.name
                kind = DOCUMENT_KIND_LABELS.get(
                    document.kind,
                    document.kind.title(),
                )
                uploaded_at = document.uploaded_at.strftime("%d-%m-%Y %H:%M")

            self.current_file_path = file_path
            self.current_sections = sections

            self.document_view.setPlainText(text)
            self.document_info.setText(
                f"{student_name}  •  V{document.version} {kind}  •  "
                f"Import: {uploaded_at}  •  {file_path.name}"
            )

            self.section_combo.blockSignals(True)
            self.section_combo.addItem("Awal Dokumen")
            self.section_combo.addItems(sections)
            self.section_combo.blockSignals(False)

        except FileNotFoundError as exc:
            self.document_info.setText(
                f"File tidak ditemukan di storage lokal: {exc}"
            )
        except Exception as exc:
            self.document_info.setText(
                f"Dokumen tidak dapat dibaca: {exc}"
            )

        self.load_comments()
        self.update_document_actions()

    def jump_to_section(self, section: str) -> None:
        if not section or section == "Awal Dokumen":
            cursor = self.document_view.textCursor()
            cursor.movePosition(QTextCursor.Start)
            self.document_view.setTextCursor(cursor)
            self.document_view.ensureCursorVisible()
            return

        document = self.document_view.document()
        cursor = document.find(section)

        if not cursor.isNull():
            self.document_view.setTextCursor(cursor)
            self.document_view.ensureCursorVisible()

    def open_original_file(self) -> None:
        if not self.current_file_path or not self.current_file_path.exists():
            QMessageBox.warning(
                self,
                "File tidak ditemukan",
                "File asli tidak tersedia di storage lokal.",
            )
            return

        opened = QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(self.current_file_path.resolve()))
        )
        if not opened:
            QMessageBox.warning(
                self,
                "File tidak dapat dibuka",
                "Windows tidak menemukan aplikasi untuk membuka file tersebut.",
            )

    def load_comments(self, *_args) -> None:
        self.comments_table.setRowCount(0)

        if self.current_document_id is None:
            self.comment_count_label.setText("0 komentar")
            self.update_comment_actions()
            return

        query = (
            select(ReviewComment)
            .where(ReviewComment.document_id == self.current_document_id)
            .order_by(ReviewComment.created_at.desc())
        )

        filter_text = self.comment_filter.currentText()
        if filter_text == "Terbuka":
            query = query.where(ReviewComment.status == "Open")
        elif filter_text == "Selesai":
            query = query.where(ReviewComment.status == "Resolved")

        with SessionLocal() as session:
            comments = session.scalars(query).all()

        self.comments_table.setRowCount(len(comments))

        for row, comment in enumerate(comments):
            values = [
                comment.section or "Umum",
                comment.content,
                COMMENT_STATUS_LABELS.get(
                    comment.status,
                    comment.status,
                ),
                comment.created_at.strftime("%d-%m-%Y %H:%M"),
            ]

            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column == 0:
                    item.setData(Qt.UserRole, comment.id)
                self.comments_table.setItem(row, column, item)

        self.comment_count_label.setText(f"{len(comments)} komentar")
        self.update_comment_actions()

    def selected_comment_id(self) -> int | None:
        selected = self.comments_table.selectionModel().selectedRows()
        if not selected:
            return None

        item = self.comments_table.item(selected[0].row(), 0)
        if item is None:
            return None

        value = item.data(Qt.UserRole)
        return int(value) if value is not None else None

    def selected_section(self) -> str:
        text = self.section_combo.currentText().strip()
        if not text or text == "Awal Dokumen":
            return "Umum"
        return text

    def add_comment(self) -> None:
        if self.current_document_id is None:
            return

        dialog = CommentDialog(
            sections=self.current_sections,
            selected_section=self.selected_section(),
            parent=self,
        )
        if dialog.exec() != QDialog.Accepted:
            return

        payload = dialog.payload()

        with SessionLocal() as session:
            session.add(
                ReviewComment(
                    document_id=self.current_document_id,
                    section=payload["section"],
                    content=payload["content"],
                    status="Open",
                )
            )
            session.commit()

        self.load_comments()

    def edit_selected_comment(self) -> None:
        comment_id = self.selected_comment_id()
        if comment_id is None:
            return

        with SessionLocal() as session:
            comment = session.get(ReviewComment, comment_id)
            if comment is None:
                self.load_comments()
                return

            dialog = CommentDialog(
                sections=self.current_sections,
                comment=comment,
                parent=self,
            )

        if dialog.exec() != QDialog.Accepted:
            return

        payload = dialog.payload()

        with SessionLocal() as session:
            comment = session.get(ReviewComment, comment_id)
            if comment is None:
                self.load_comments()
                return

            comment.section = payload["section"]
            comment.content = payload["content"]
            session.commit()

        self.load_comments()

    def toggle_selected_status(self) -> None:
        comment_id = self.selected_comment_id()
        if comment_id is None:
            return

        with SessionLocal() as session:
            comment = session.get(ReviewComment, comment_id)
            if comment is None:
                self.load_comments()
                return

            comment.status = (
                "Resolved" if comment.status == "Open" else "Open"
            )
            session.commit()

        self.load_comments()

    def delete_selected_comment(self) -> None:
        comment_id = self.selected_comment_id()
        if comment_id is None:
            return

        with SessionLocal() as session:
            comment = session.get(ReviewComment, comment_id)
            if comment is None:
                self.load_comments()
                return

            preview = comment.content
            if len(preview) > 180:
                preview = preview[:177] + "..."

            answer = QMessageBox.question(
                self,
                "Hapus komentar",
                (
                    "Yakin ingin menghapus komentar berikut?\n\n"
                    f"{preview}\n\n"
                    "Tindakan ini tidak dapat dibatalkan."
                ),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return

            session.delete(comment)
            session.commit()

        self.load_comments()

    def update_document_actions(self) -> None:
        has_document = self.current_document_id is not None
        has_file = (
            self.current_file_path is not None
            and self.current_file_path.exists()
        )

        self.add_comment_button.setEnabled(has_document)
        self.open_file_button.setEnabled(has_file)
        self.section_combo.setEnabled(has_document)

    def update_comment_actions(self) -> None:
        comment_id = self.selected_comment_id()
        has_selection = comment_id is not None

        self.edit_comment_button.setEnabled(has_selection)
        self.toggle_status_button.setEnabled(has_selection)
        self.delete_comment_button.setEnabled(has_selection)

        if not has_selection:
            self.toggle_status_button.setText("Tandai Selesai")
            return

        with SessionLocal() as session:
            comment = session.get(ReviewComment, comment_id)
            if comment and comment.status == "Resolved":
                self.toggle_status_button.setText("Buka Kembali")
            else:
                self.toggle_status_button.setText("Tandai Selesai")
