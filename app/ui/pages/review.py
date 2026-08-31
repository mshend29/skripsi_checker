from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Qt, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QSplitter,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import SessionLocal
from app.models import ReviewComment, Thesis, ThesisDocument
from app.services.docx_html_service import write_docx_html_preview
from app.services.document_service import (
    export_docx_with_comments,
    extract_review_paragraphs,
    extract_review_structure,
    resolve_storage_path,
)


DOCUMENT_KIND_LABELS = {
    "proposal": "Proposal",
    "revision": "Revisi",
    "final": "Final",
}

CATEGORY_OPTIONS = [
    "Substansi",
    "Metodologi",
    "Bahasa",
    "Format",
    "Sitasi",
    "Referensi",
    "Data",
    "Umum",
]

SEVERITY_OPTIONS = [
    "Minor",
    "Moderate",
    "Major",
    "Critical",
]

STATUS_LABELS = {
    "Open": "Belum Diperbaiki",
    "Resolved": "Selesai",
}


class ReviewBridge(QObject):
    comment_requested = Signal(int, str)

    @Slot(int, str)
    def requestComment(self, paragraph_index: int, selected_text: str) -> None:
        self.comment_requested.emit(paragraph_index, selected_text)


class CommentDialog(QDialog):
    def __init__(
        self,
        paragraph_text: str,
        selected_text: str,
        section: str,
        comment_data: dict | None = None,
        parent=None,
    ):
        super().__init__(parent)

        self.setWindowTitle(
            "Edit Komentar" if comment_data else "Tambah Komentar"
        )
        self.resize(780, 650)
        self.setMinimumSize(720, 590)
        self.setStyleSheet(
            "QDialog { background: #f3f3f3; }"
            "QLabel { color: #111111; }"
            "QComboBox {"
            " background: #ffffff;"
            " color: #111111;"
            " border: 1px solid #c4c4c4;"
            " border-radius: 5px;"
            " padding: 6px 8px;"
            " font-size: 13px;"
            "}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        location = QLabel(
            f"<b>Bagian:</b> {section or 'Awal Dokumen'}"
        )
        location.setWordWrap(True)
        location.setStyleSheet("font-size: 13px; color: #111111;")
        layout.addWidget(location)

        quote_label = QLabel("Kutipan / teks yang dikoreksi")
        quote_label.setStyleSheet(
            "font-weight: 700; font-size: 14px; color: #111111;"
        )
        layout.addWidget(quote_label)

        self.selected_text_input = QTextEdit()
        self.selected_text_input.setPlainText(selected_text)
        self.selected_text_input.setMaximumHeight(145)
        self.selected_text_input.setPlaceholderText(
            "Kutipan paragraf yang menjadi fokus komentar."
        )
        self.selected_text_input.setStyleSheet(
            "QTextEdit {"
            " background: #ffffff;"
            " color: #000000;"
            " border: 1px solid #c2c2c2;"
            " border-radius: 6px;"
            " padding: 10px;"
            " font-size: 14px;"
            "}"
        )
        layout.addWidget(self.selected_text_input)

        form = QFormLayout()
        form.setSpacing(10)

        self.category = QComboBox()
        self.category.addItems(CATEGORY_OPTIONS)

        self.severity = QComboBox()
        self.severity.addItems(SEVERITY_OPTIONS)
        self.severity.setCurrentText("Moderate")

        form.addRow("Kategori", self.category)
        form.addRow("Tingkat", self.severity)
        layout.addLayout(form)

        correction_label = QLabel("Teks koreksi / arahan revisi")
        correction_label.setStyleSheet(
            "font-weight: 700; font-size: 14px; color: #111111;"
        )
        layout.addWidget(correction_label)

        self.content = QTextEdit()
        self.content.setPlaceholderText(
            "Tuliskan koreksi atau arahan revisi untuk mahasiswa..."
        )
        self.content.setStyleSheet(
            "QTextEdit {"
            " background: #ffffff;"
            " color: #000000;"
            " border: 1px solid #bdbdbd;"
            " border-radius: 6px;"
            " padding: 10px;"
            " font-size: 14px;"
            "}"
        )
        layout.addWidget(self.content, 1)

        if comment_data:
            if comment_data.get("category"):
                self.category.setCurrentText(comment_data["category"])
            if comment_data.get("severity"):
                self.severity.setCurrentText(comment_data["severity"])
            self.content.setPlainText(comment_data.get("content") or "")

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
        return {
            "selected_text": self.selected_text_input.toPlainText().strip(),
            "category": self.category.currentText(),
            "severity": self.severity.currentText(),
            "content": self.content.toPlainText().strip(),
        }


class CommentCard(QFrame):
    goto_requested = Signal(int)
    edit_requested = Signal(int)
    toggle_requested = Signal(int)
    delete_requested = Signal(int)

    def __init__(self, comment: dict, parent=None):
        super().__init__(parent)

        self.comment_id = int(comment["id"])
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet(
            "QFrame {"
            " background: #ffffff;"
            " border: 1px solid #dedede;"
            " border-radius: 8px;"
            "}"
            "QLabel { border: none; color: #111111; }"
            "QPushButton {"
            " background: #ffffff;"
            " color: #111111;"
            " border: 1px solid #d0d0d0;"
            " border-radius: 5px;"
            " padding: 5px 7px;"
            "}"
            "QPushButton:hover { background: #f1f1f1; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(7)

        severity = QLabel(comment.get("severity") or "Moderate")
        severity.setStyleSheet(
            "background: #efefef; border-radius: 7px; "
            "padding: 2px 6px; font-size: 10px;"
        )
        layout.addWidget(severity)

        category = QLabel(comment.get("category") or "Umum")
        category.setStyleSheet(
            "background: #f5f5f5; border-radius: 7px; "
            "padding: 2px 6px; font-size: 10px;"
        )
        layout.addWidget(category)

        status = QLabel(
            STATUS_LABELS.get(comment.get("status"), comment.get("status"))
        )
        status.setStyleSheet(
            "background: #f5f5f5; border-radius: 7px; "
            "padding: 2px 6px; font-size: 10px;"
        )
        layout.addWidget(status)

        section = QLabel(comment.get("section") or "Awal Dokumen")
        section.setWordWrap(True)
        section.setStyleSheet("font-weight: 600; color: #555555;")
        layout.addWidget(section)

        selected = (comment.get("selected_text") or "").strip()
        if selected:
            quote = QLabel(
                f'“{selected[:220]}{"…" if len(selected) > 220 else ""}”'
            )
            quote.setWordWrap(True)
            quote.setStyleSheet(
                "background: #fafafa; padding: 7px; color: #555555; "
                "font-style: italic;"
            )
            layout.addWidget(quote)

        body = QLabel(comment.get("content") or "")
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(body)

        timestamp = QLabel(comment.get("created_at") or "")
        timestamp.setStyleSheet("color: #999999; font-size: 10px;")
        layout.addWidget(timestamp)

        goto_button = QPushButton("Ke paragraf")
        goto_button.clicked.connect(
            lambda: self.goto_requested.emit(self.comment_id)
        )
        layout.addWidget(goto_button)

        edit_button = QPushButton("Edit")
        edit_button.clicked.connect(
            lambda: self.edit_requested.emit(self.comment_id)
        )
        layout.addWidget(edit_button)

        toggle_text = (
            "Buka Lagi"
            if comment.get("status") == "Resolved"
            else "Selesai"
        )
        toggle_button = QPushButton(toggle_text)
        toggle_button.clicked.connect(
            lambda: self.toggle_requested.emit(self.comment_id)
        )
        layout.addWidget(toggle_button)

        delete_button = QPushButton("Hapus")
        delete_button.clicked.connect(
            lambda: self.delete_requested.emit(self.comment_id)
        )
        layout.addWidget(delete_button)


class ReviewPage(QWidget):
    def __init__(self):
        super().__init__()

        self.current_document_id: int | None = None
        self.current_file_path: Path | None = None
        self.current_paragraphs: list[dict] = []
        self._loading = False
        self._pending_scroll_paragraph: int | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)

        header = QHBoxLayout()
        title_box = QVBoxLayout()

        title = QLabel("Review Dokumen")
        title.setStyleSheet("font-size: 26px; font-weight: 700;")
        subtitle = QLabel(
            "DOCX dirender langsung sebagai dokumen HTML interaktif. "
            "Blok teks seperti di browser lalu tambahkan komentar."
        )
        subtitle.setStyleSheet("color: #666666;")
        subtitle.setWordWrap(True)

        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box)
        header.addStretch()

        self.export_button = QPushButton("Export Word Berkomentar")
        self.export_button.clicked.connect(self.export_word_comments)
        header.addWidget(self.export_button)

        root.addLayout(header)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        toolbar.addWidget(QLabel("Skripsi"))
        self.thesis_combo = QComboBox()
        self.thesis_combo.setMinimumWidth(280)
        self.thesis_combo.currentIndexChanged.connect(self.load_documents)
        toolbar.addWidget(self.thesis_combo, 2)

        toolbar.addWidget(QLabel("Dokumen"))
        self.document_combo = QComboBox()
        self.document_combo.setMinimumWidth(190)
        self.document_combo.currentIndexChanged.connect(self.load_document)
        toolbar.addWidget(self.document_combo, 1)

        self.open_button = QPushButton("Buka File Asli")
        self.open_button.clicked.connect(self.open_original_file)
        toolbar.addWidget(self.open_button)

        toolbar.addSpacing(8)
        toolbar.addWidget(QLabel("Zoom"))

        self.zoom_out_button = QPushButton("−")
        self.zoom_out_button.setFixedWidth(30)
        self.zoom_out_button.clicked.connect(
            lambda: self.change_zoom(-10)
        )
        toolbar.addWidget(self.zoom_out_button)

        self.zoom_slider = QSlider(Qt.Horizontal)
        self.zoom_slider.setRange(50, 200)
        self.zoom_slider.setSingleStep(10)
        self.zoom_slider.setPageStep(10)
        self.zoom_slider.setValue(100)
        self.zoom_slider.setFixedWidth(110)
        self.zoom_slider.valueChanged.connect(self.apply_zoom)
        toolbar.addWidget(self.zoom_slider)

        self.zoom_in_button = QPushButton("+")
        self.zoom_in_button.setFixedWidth(30)
        self.zoom_in_button.clicked.connect(
            lambda: self.change_zoom(10)
        )
        toolbar.addWidget(self.zoom_in_button)

        self.zoom_label = QLabel("100%")
        self.zoom_label.setFixedWidth(45)
        self.zoom_label.setAlignment(Qt.AlignCenter)
        toolbar.addWidget(self.zoom_label)

        root.addLayout(toolbar)

        self.version_info = QLabel("Pilih skripsi untuk mulai review.")
        self.version_info.setStyleSheet("color: #777777; font-size: 12px;")
        self.version_info.setWordWrap(True)
        root.addWidget(self.version_info)

        self.review_splitter = QSplitter(Qt.Horizontal)
        self.review_splitter.setChildrenCollapsible(False)
        root.addWidget(self.review_splitter, 1)

        self.review_splitter.addWidget(self.build_structure_panel())
        self.review_splitter.addWidget(self.build_document_panel())
        self.review_splitter.addWidget(self.build_comments_panel())

        self.review_splitter.setStretchFactor(0, 2)
        self.review_splitter.setStretchFactor(1, 7)
        self.review_splitter.setStretchFactor(2, 1)
        self.review_splitter.setSizes([200, 700, 100])

        self.update_actions()

    def build_structure_panel(self) -> QWidget:
        panel = QFrame()
        panel.setMinimumWidth(120)
        panel.setFrameShape(QFrame.StyledPanel)
        panel.setStyleSheet(
            "QFrame { background: #ffffff; border: 1px solid #d9d9d9; }"
            "QLabel { border: none; color: #111111; }"
        )

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)

        heading = QHBoxLayout()
        title = QLabel("STRUKTUR")
        title.setStyleSheet("font-weight: 700;")
        heading.addWidget(title)
        heading.addStretch()

        self.section_count = QLabel("0")
        self.section_count.setStyleSheet(
            "background: #f1f1f1; border-radius: 8px; padding: 2px 7px;"
        )
        heading.addWidget(self.section_count)
        layout.addLayout(heading)

        self.structure_tree = QTreeWidget()
        self.structure_tree.setHeaderHidden(True)
        self.structure_tree.setRootIsDecorated(False)
        self.structure_tree.setIndentation(16)
        self.structure_tree.setAnimated(True)
        self.structure_tree.setStyleSheet(
            "QTreeWidget {"
            " background: #ffffff;"
            " color: #111111;"
            " border: none;"
            " outline: none;"
            "}"
            "QTreeWidget::item { padding: 5px 3px; border-radius: 4px; }"
            "QTreeWidget::item:hover { background: #f2f2f2; }"
            "QTreeWidget::item:selected {"
            " background: #e8e8e8;"
            " color: #000000;"
            "}"
        )
        self.structure_tree.itemClicked.connect(self.goto_structure_item)
        self.structure_tree.itemExpanded.connect(
            self.update_tree_item_indicator
        )
        self.structure_tree.itemCollapsed.connect(
            self.update_tree_item_indicator
        )
        layout.addWidget(self.structure_tree, 1)

        return panel

    def build_document_panel(self) -> QWidget:
        panel = QFrame()
        panel.setFrameShape(QFrame.NoFrame)
        panel.setStyleSheet("background: #d8d8d8;")

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        self.web_view = QWebEngineView()
        self.web_view.setStyleSheet("background: #d8d8d8;")

        self.review_bridge = ReviewBridge()
        self.review_bridge.comment_requested.connect(
            self.add_comment_for_paragraph
        )

        self.web_channel = QWebChannel(self.web_view.page())
        self.web_channel.registerObject("reviewBridge", self.review_bridge)
        self.web_view.page().setWebChannel(self.web_channel)
        self.web_view.loadFinished.connect(self.on_web_loaded)

        layout.addWidget(self.web_view, 1)
        return panel

    def build_comments_panel(self) -> QWidget:
        panel = QFrame()
        panel.setMinimumWidth(95)
        panel.setFrameShape(QFrame.StyledPanel)
        panel.setStyleSheet(
            "QFrame { background: #f7f7f7; border: 1px solid #dedede; }"
            "QLabel { border: none; color: #111111; }"
        )

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(7)

        title = QLabel("CATATAN REVIEW")
        title.setWordWrap(True)
        title.setStyleSheet("font-weight: 700;")
        layout.addWidget(title)

        self.comment_filter = QComboBox()
        self.comment_filter.addItems(["Aktif", "Semua", "Selesai"])
        self.comment_filter.currentTextChanged.connect(self.load_comments)
        layout.addWidget(self.comment_filter)

        self.comment_count = QLabel("0 komentar")
        self.comment_count.setStyleSheet("color: #777777; font-size: 10px;")
        self.comment_count.setWordWrap(True)
        layout.addWidget(self.comment_count)

        self.comments_scroll = QScrollArea()
        self.comments_scroll.setWidgetResizable(True)
        self.comments_scroll.setFrameShape(QFrame.NoFrame)

        self.comments_container = QWidget()
        self.comments_layout = QVBoxLayout(self.comments_container)
        self.comments_layout.setContentsMargins(0, 0, 0, 0)
        self.comments_layout.setSpacing(7)
        self.comments_layout.addStretch()

        self.comments_scroll.setWidget(self.comments_container)
        layout.addWidget(self.comments_scroll, 1)

        return panel

    def refresh(self) -> None:
        selected_thesis_id = self.thesis_combo.currentData()

        with SessionLocal() as session:
            theses = session.scalars(
                select(Thesis)
                .options(
                    selectinload(Thesis.student),
                    selectinload(Thesis.documents),
                )
                .order_by(Thesis.id.desc())
            ).all()

        self._loading = True
        self.thesis_combo.clear()

        for thesis in theses:
            self.thesis_combo.addItem(
                f"{thesis.student.name} — "
                f"{thesis.title or '(judul belum tersedia)'}",
                thesis.id,
            )

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
                self.document_combo.addItem(
                    f"V{document.version} — {kind}",
                    document.id,
                )

        self._loading = False
        self.load_document()

    def load_document(self, *_args) -> None:
        if self._loading:
            return

        self.current_document_id = self.document_combo.currentData()
        self.current_file_path = None
        self.current_paragraphs = []
        self._pending_scroll_paragraph = None
        self.clear_structure()

        if self.current_document_id is None:
            self.version_info.setText(
                "Skripsi ini belum mempunyai dokumen untuk direview."
            )
            self.web_view.setHtml(
                self.empty_document_html(
                    "Belum ada dokumen yang dapat ditampilkan."
                )
            )
            self.load_comments()
            self.update_actions()
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
                    .where(ThesisDocument.id == self.current_document_id)
                )

                if document is None:
                    raise ValueError("Dokumen tidak ditemukan.")

                file_path = resolve_storage_path(document.file_path)
                if not file_path.exists():
                    raise FileNotFoundError(str(file_path))

                meta = {
                    "version": document.version,
                    "kind": document.kind,
                    "uploaded_at": document.uploaded_at,
                    "student": document.thesis.student.name,
                }

            self.current_file_path = file_path
            self.current_paragraphs = extract_review_paragraphs(file_path)
            structure = extract_review_structure(
                file_path,
                paragraphs=self.current_paragraphs,
            )
            self.populate_structure(structure)

            counts = self.comment_counts_by_paragraph()

            if file_path.suffix.lower() == ".docx":
                preview_html = write_docx_html_preview(
                    file_path,
                    comment_counts=counts,
                )
                self.web_view.load(
                    QUrl.fromLocalFile(str(preview_html.resolve()))
                )
                mode_text = "HTML interaktif langsung dari DOCX"
            else:
                self.web_view.setHtml(
                    self.empty_document_html(
                        "Mode koreksi interaktif saat ini diprioritaskan "
                        "untuk DOCX. Gunakan file DOCX agar teks dapat "
                        "diblok, tabel/gambar ditampilkan, dan komentar "
                        "menempel langsung pada paragraf."
                    )
                )
                mode_text = "PDF: mode terbatas"

            kind = DOCUMENT_KIND_LABELS.get(
                meta["kind"],
                meta["kind"].title(),
            )
            self.version_info.setText(
                f'{meta["student"]}  •  '
                f'V{meta["version"]} {kind}  •  '
                f'{meta["uploaded_at"].strftime("%d-%m-%Y %H:%M")}  •  '
                f'{file_path.name}  •  {mode_text}'
            )

        except Exception as exc:
            self.web_view.setHtml(
                self.empty_document_html(
                    f"Dokumen tidak dapat ditampilkan: {exc}"
                )
            )
            self.version_info.setText(
                f"Dokumen tidak dapat ditampilkan: {exc}"
            )

        self.load_comments()
        self.update_actions()

    def empty_document_html(self, message: str) -> str:
        safe = (
            message.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        return (
            "<html><body style='margin:0;background:#d8d8d8;"
            "font-family:Arial;color:#333;'>"
            "<div style='max-width:720px;margin:80px auto;"
            "background:white;padding:32px;border-radius:8px;"
            "box-shadow:0 2px 10px rgba(0,0,0,.15);'>"
            f"{safe}</div></body></html>"
        )

    def populate_structure(self, structure: list[dict]) -> None:
        self.structure_tree.clear()

        def add_node(parent, node: dict) -> None:
            item = QTreeWidgetItem()
            label = node.get("label") or "Bagian"
            item.setData(0, Qt.UserRole, node.get("paragraph_index"))
            item.setData(0, Qt.UserRole + 1, label)

            if parent is None:
                self.structure_tree.addTopLevelItem(item)
            else:
                parent.addChild(item)

            for child in node.get("children") or []:
                add_node(item, child)

            self.update_tree_item_indicator(item)

        for node in structure:
            add_node(None, node)

        self.structure_tree.collapseAll()
        self.section_count.setText(str(len(structure)))

    def update_tree_item_indicator(
        self,
        item: QTreeWidgetItem,
    ) -> None:
        label = item.data(0, Qt.UserRole + 1) or item.text(0)
        prefix = ""
        if item.childCount():
            prefix = "−  " if item.isExpanded() else "+  "
        else:
            prefix = "   "

        item.setText(0, f"{prefix}{label}")

    def clear_structure(self) -> None:
        self.structure_tree.clear()
        self.section_count.setText("0")

    def goto_structure_item(
        self,
        item: QTreeWidgetItem,
        _column: int,
    ) -> None:
        if item.childCount():
            item.setExpanded(not item.isExpanded())

        paragraph_index = item.data(0, Qt.UserRole)
        if paragraph_index is not None:
            self.scroll_to_paragraph(int(paragraph_index))

    def scroll_to_paragraph(self, paragraph_index: int) -> None:
        self.web_view.page().runJavaScript(
            f"window.scrollToParagraph && "
            f"window.scrollToParagraph({int(paragraph_index)});"
        )

    def on_web_loaded(self, ok: bool) -> None:
        if not ok:
            return

        self.apply_zoom(self.zoom_slider.value())

        if self._pending_scroll_paragraph is not None:
            paragraph_index = self._pending_scroll_paragraph
            self._pending_scroll_paragraph = None
            self.scroll_to_paragraph(paragraph_index)

    def apply_zoom(self, value: int) -> None:
        self.zoom_label.setText(f"{value}%")
        self.web_view.setZoomFactor(value / 100.0)

    def change_zoom(self, delta: int) -> None:
        self.zoom_slider.setValue(
            max(
                self.zoom_slider.minimum(),
                min(
                    self.zoom_slider.maximum(),
                    self.zoom_slider.value() + delta,
                ),
            )
        )

    def paragraph_data(self, paragraph_index: int) -> dict | None:
        for paragraph in self.current_paragraphs:
            if int(paragraph["paragraph_index"]) == paragraph_index:
                return paragraph
        return None

    def add_comment_for_paragraph(
        self,
        paragraph_index: int,
        selected_text: str,
    ) -> None:
        if self.current_document_id is None:
            return

        paragraph = self.paragraph_data(paragraph_index)
        if paragraph is None:
            return

        quote = selected_text.strip() or paragraph["text"]

        dialog = CommentDialog(
            paragraph_text=paragraph["text"],
            selected_text=quote,
            section=paragraph.get("section") or "Awal Dokumen",
            parent=self,
        )
        if dialog.exec() != QDialog.Accepted:
            return

        payload = dialog.payload()

        with SessionLocal() as session:
            session.add(
                ReviewComment(
                    document_id=self.current_document_id,
                    section=paragraph.get("section") or "Awal Dokumen",
                    paragraph_index=paragraph_index,
                    selected_text=payload["selected_text"] or quote,
                    category=payload["category"],
                    severity=payload["severity"],
                    content=payload["content"],
                    status="Open",
                )
            )
            session.commit()

        self._pending_scroll_paragraph = paragraph_index
        self.load_document()

    def comment_counts_by_paragraph(self) -> dict[int, int]:
        if self.current_document_id is None:
            return {}

        with SessionLocal() as session:
            comments = session.scalars(
                select(ReviewComment).where(
                    ReviewComment.document_id == self.current_document_id,
                    ReviewComment.status != "Resolved",
                )
            ).all()

        result: dict[int, int] = {}
        for comment in comments:
            if comment.paragraph_index is None:
                continue

            index = int(comment.paragraph_index)
            result[index] = result.get(index, 0) + 1

        return result

    def clear_comments_layout(self) -> None:
        while self.comments_layout.count() > 1:
            item = self.comments_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def load_comments(self, *_args) -> None:
        self.clear_comments_layout()

        if self.current_document_id is None:
            self.comment_count.setText("0 komentar")
            return

        query = (
            select(ReviewComment)
            .where(ReviewComment.document_id == self.current_document_id)
            .order_by(ReviewComment.created_at.desc())
        )

        filter_text = self.comment_filter.currentText()
        if filter_text == "Aktif":
            query = query.where(ReviewComment.status != "Resolved")
        elif filter_text == "Selesai":
            query = query.where(ReviewComment.status == "Resolved")

        with SessionLocal() as session:
            comments = session.scalars(query).all()

            rows = [
                {
                    "id": comment.id,
                    "section": comment.section,
                    "paragraph_index": comment.paragraph_index,
                    "selected_text": comment.selected_text,
                    "category": comment.category,
                    "severity": comment.severity,
                    "content": comment.content,
                    "status": comment.status,
                    "created_at": comment.created_at.strftime(
                        "%d-%m-%Y %H:%M"
                    ),
                }
                for comment in comments
            ]

        active_count = sum(
            1 for row in rows if row["status"] != "Resolved"
        )
        self.comment_count.setText(
            f"{active_count} aktif\n{len(rows)} tampil"
        )

        if not rows:
            empty = QLabel(
                "Belum ada komentar.\n"
                "Hover paragraf atau blok teks di dokumen."
            )
            empty.setAlignment(Qt.AlignCenter)
            empty.setWordWrap(True)
            empty.setStyleSheet("color: #888888; padding: 18px 4px;")
            self.comments_layout.insertWidget(
                self.comments_layout.count() - 1,
                empty,
            )
            return

        for row in rows:
            card = CommentCard(row)
            card.goto_requested.connect(self.goto_comment)
            card.edit_requested.connect(self.edit_comment)
            card.toggle_requested.connect(self.toggle_comment)
            card.delete_requested.connect(self.delete_comment)

            self.comments_layout.insertWidget(
                self.comments_layout.count() - 1,
                card,
            )

    def goto_comment(self, comment_id: int) -> None:
        with SessionLocal() as session:
            comment = session.get(ReviewComment, comment_id)
            if comment is None or comment.paragraph_index is None:
                return

            paragraph_index = int(comment.paragraph_index)

        self.scroll_to_paragraph(paragraph_index)

    def edit_comment(self, comment_id: int) -> None:
        with SessionLocal() as session:
            comment = session.get(ReviewComment, comment_id)
            if comment is None:
                return

            paragraph_index = comment.paragraph_index
            selected_text = comment.selected_text or ""
            section = comment.section or "Awal Dokumen"
            data = {
                "category": comment.category,
                "severity": comment.severity,
                "content": comment.content,
            }

        paragraph = (
            self.paragraph_data(int(paragraph_index))
            if paragraph_index is not None
            else None
        )

        dialog = CommentDialog(
            paragraph_text=paragraph["text"] if paragraph else "",
            selected_text=selected_text,
            section=section,
            comment_data=data,
            parent=self,
        )
        if dialog.exec() != QDialog.Accepted:
            return

        payload = dialog.payload()

        with SessionLocal() as session:
            comment = session.get(ReviewComment, comment_id)
            if comment is None:
                return

            comment.selected_text = (
                payload["selected_text"] or comment.selected_text
            )
            comment.category = payload["category"]
            comment.severity = payload["severity"]
            comment.content = payload["content"]
            session.commit()

        self.load_comments()

    def toggle_comment(self, comment_id: int) -> None:
        paragraph_index = None

        with SessionLocal() as session:
            comment = session.get(ReviewComment, comment_id)
            if comment is None:
                return

            paragraph_index = comment.paragraph_index
            comment.status = (
                "Resolved"
                if comment.status != "Resolved"
                else "Open"
            )
            session.commit()

        if paragraph_index is not None:
            self._pending_scroll_paragraph = int(paragraph_index)

        self.load_document()

    def delete_comment(self, comment_id: int) -> None:
        paragraph_index = None

        with SessionLocal() as session:
            comment = session.get(ReviewComment, comment_id)
            if comment is None:
                return

            paragraph_index = comment.paragraph_index
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

        if paragraph_index is not None:
            self._pending_scroll_paragraph = int(paragraph_index)

        self.load_document()

    def open_original_file(self) -> None:
        if (
            self.current_file_path is None
            or not self.current_file_path.exists()
        ):
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

    def export_word_comments(self) -> None:
        if (
            self.current_document_id is None
            or self.current_file_path is None
        ):
            return

        if self.current_file_path.suffix.lower() != ".docx":
            QMessageBox.information(
                self,
                "Export Word",
                "Export komentar Word native hanya tersedia untuk DOCX.",
            )
            return

        with SessionLocal() as session:
            comments = session.scalars(
                select(ReviewComment)
                .where(
                    ReviewComment.document_id == self.current_document_id,
                    ReviewComment.status != "Resolved",
                )
                .order_by(ReviewComment.paragraph_index.asc())
            ).all()

            export_rows = [
                {
                    "paragraph_index": comment.paragraph_index,
                    "selected_text": comment.selected_text,
                    "category": comment.category,
                    "severity": comment.severity,
                    "content": comment.content,
                }
                for comment in comments
                if comment.paragraph_index is not None
            ]

        if not export_rows:
            QMessageBox.information(
                self,
                "Tidak ada komentar aktif",
                "Tidak ada komentar aktif untuk diekspor ke Word.",
            )
            return

        default_name = self.current_file_path.stem + "_koreksi.docx"
        output_path, _ = QFileDialog.getSaveFileName(
            self,
            "Simpan Word Berkomentar",
            str(self.current_file_path.parent / default_name),
            "Word Document (*.docx)",
        )
        if not output_path:
            return

        if not output_path.lower().endswith(".docx"):
            output_path += ".docx"

        try:
            exported = export_docx_with_comments(
                source_path=self.current_file_path,
                output_path=output_path,
                comments=export_rows,
            )
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Export gagal",
                f"File Word berkomentar tidak dapat dibuat.\n\n{exc}",
            )
            return

        QMessageBox.information(
            self,
            "Export berhasil",
            (
                f"{exported} komentar aktif berhasil ditanamkan ke Word.\n\n"
                f"{output_path}"
            ),
        )

    def update_actions(self) -> None:
        has_file = (
            self.current_file_path is not None
            and self.current_file_path.exists()
        )
        is_docx = (
            has_file
            and self.current_file_path.suffix.lower() == ".docx"
        )

        self.open_button.setEnabled(has_file)
        self.export_button.setEnabled(bool(is_docx))
