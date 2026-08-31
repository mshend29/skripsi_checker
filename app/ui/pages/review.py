from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QTreeWidget,
    QTreeWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import SessionLocal
from app.models import ReviewComment, Thesis, ThesisDocument
from app.services.document_service import (
    ensure_preview_pdf,
    export_docx_with_comments,
    extract_review_paragraphs,
    extract_review_structure,
    map_review_paragraphs_to_preview,
    render_preview_pages,
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


class PreviewParagraphOverlay(QFrame):
    comment_requested = Signal(int, str)

    def __init__(
        self,
        anchor: dict,
        comment_count: int = 0,
        parent=None,
    ):
        super().__init__(parent)

        self.anchor = anchor
        self._hovered = False
        self._highlighted = False

        self.setObjectName("previewParagraphOverlay")
        self.setMouseTracking(True)
        self.setAttribute(Qt.WA_StyledBackground, True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.addStretch()

        if comment_count:
            badge = QLabel(str(comment_count))
            badge.setFixedSize(22, 18)
            badge.setAlignment(Qt.AlignCenter)
            badge.setToolTip(f"{comment_count} catatan aktif")
            badge.setStyleSheet(
                "background: rgba(255,255,255,235);"
                "color: #111111;"
                "border: 1px solid #bdbdbd;"
                "border-radius: 8px;"
                "font-size: 9px;"
            )
            layout.addWidget(badge)

        self.comment_button = QPushButton("+ Komentar")
        self.comment_button.setCursor(Qt.PointingHandCursor)
        self.comment_button.setStyleSheet(
            "QPushButton {"
            " background: rgba(255,255,255,245);"
            " color: #111111;"
            " border: 1px solid #a9a9a9;"
            " border-radius: 4px;"
            " padding: 4px 7px;"
            " font-size: 10px;"
            "}"
            "QPushButton:hover { background: #f2f2f2; }"
        )
        self.comment_button.clicked.connect(self.request_comment)
        self.comment_button.hide()
        layout.addWidget(self.comment_button)

        self._apply_style()

    def _apply_style(self) -> None:
        if self._highlighted:
            border = "2px solid rgba(90,90,90,220)"
            background = "rgba(255,248,190,55)"
        elif self._hovered:
            border = "1px solid rgba(110,110,110,180)"
            background = "rgba(255,255,255,20)"
        else:
            border = "1px solid rgba(0,0,0,0)"
            background = "rgba(255,255,255,0)"

        self.setStyleSheet(
            "QFrame#previewParagraphOverlay {"
            f"border: {border};"
            f"background: {background};"
            "border-radius: 3px;"
            "}"
        )

    def set_highlighted(self, highlighted: bool) -> None:
        self._highlighted = highlighted
        self.comment_button.setVisible(highlighted or self._hovered)
        self._apply_style()

    def enterEvent(self, event) -> None:
        self._hovered = True
        self.comment_button.show()
        self._apply_style()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self.comment_button.setVisible(self._highlighted)
        self._apply_style()
        super().leaveEvent(event)

    def request_comment(self) -> None:
        self.comment_requested.emit(
            int(self.anchor["paragraph_index"]),
            self.anchor.get("text") or "",
        )


class PreviewPageWidget(QFrame):
    comment_requested = Signal(int, str)

    def __init__(
        self,
        page_data: dict,
        anchors: list[dict],
        comment_counts: dict[int, int],
        parent=None,
    ):
        super().__init__(parent)

        self.overlay_widgets: dict[int, PreviewParagraphOverlay] = {}

        pixmap = QPixmap()
        pixmap.loadFromData(page_data["png"])

        self.setObjectName("previewPage")
        self.setFixedSize(
            int(page_data["image_width"]) + 2,
            int(page_data["image_height"]) + 2,
        )
        self.setStyleSheet(
            "QFrame#previewPage {"
            " background: #ffffff;"
            " border: 1px solid #bdbdbd;"
            "}"
        )

        image = QLabel(self)
        image.setPixmap(pixmap)
        image.setGeometry(
            1,
            1,
            int(page_data["image_width"]),
            int(page_data["image_height"]),
        )
        image.lower()

        scale_x = (
            float(page_data["image_width"])
            / float(page_data["page_width"])
        )
        scale_y = (
            float(page_data["image_height"])
            / float(page_data["page_height"])
        )

        for anchor in anchors:
            x0, y0, x1, y1 = anchor["bbox"]

            left = max(1, int(x0 * scale_x) + 1)
            top = max(1, int(y0 * scale_y) + 1)
            width = max(44, int((x1 - x0) * scale_x))
            height = max(24, int((y1 - y0) * scale_y))

            right_limit = int(page_data["image_width"]) - 2
            bottom_limit = int(page_data["image_height"]) - 2

            if left + width > right_limit:
                width = max(20, right_limit - left)
            if top + height > bottom_limit:
                height = max(20, bottom_limit - top)

            paragraph_index = int(anchor["paragraph_index"])
            overlay = PreviewParagraphOverlay(
                anchor=anchor,
                comment_count=comment_counts.get(paragraph_index, 0),
                parent=self,
            )
            overlay.setGeometry(left, top, width, height)
            overlay.comment_requested.connect(
                self.comment_requested.emit
            )
            overlay.raise_()

            self.overlay_widgets[paragraph_index] = overlay


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
        self.resize(600, 500)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        location = QLabel(
            f"<b>Bagian:</b> {section or 'Awal Dokumen'}"
        )
        location.setWordWrap(True)
        layout.addWidget(location)

        quote_label = QLabel("Kutipan / teks yang dikoreksi")
        quote_label.setStyleSheet("font-weight: 600;")
        layout.addWidget(quote_label)

        self.selected_text_input = QTextEdit()
        self.selected_text_input.setPlainText(selected_text)
        self.selected_text_input.setMaximumHeight(95)
        self.selected_text_input.setPlaceholderText(
            "Kutipan paragraf yang menjadi fokus komentar."
        )
        self.selected_text_input.setStyleSheet(
            "background: #f7f7f7; color: #111111;"
        )
        layout.addWidget(self.selected_text_input)

        form = QFormLayout()

        self.category = QComboBox()
        self.category.addItems(CATEGORY_OPTIONS)

        self.severity = QComboBox()
        self.severity.addItems(SEVERITY_OPTIONS)
        self.severity.setCurrentText("Moderate")

        form.addRow("Kategori", self.category)
        form.addRow("Tingkat", self.severity)
        layout.addLayout(form)

        self.content = QTextEdit()
        self.content.setPlaceholderText(
            "Tuliskan koreksi atau arahan revisi untuk mahasiswa..."
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
            "QFrame { background: white; border: 1px solid #dedede; "
            "border-radius: 8px; }"
            "QLabel { border: none; }"
            "QPushButton { border: 1px solid #d5d5d5; "
            "border-radius: 5px; padding: 5px 8px; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        badges = QHBoxLayout()
        severity = QLabel(comment.get("severity") or "Moderate")
        severity.setStyleSheet(
            "background: #efefef; border-radius: 8px; "
            "padding: 2px 7px; font-size: 10px;"
        )
        category = QLabel(comment.get("category") or "Umum")
        category.setStyleSheet(
            "background: #f5f5f5; border-radius: 8px; "
            "padding: 2px 7px; font-size: 10px;"
        )
        status = QLabel(
            STATUS_LABELS.get(comment.get("status"), comment.get("status"))
        )
        status.setStyleSheet(
            "background: #f5f5f5; border-radius: 8px; "
            "padding: 2px 7px; font-size: 10px;"
        )

        badges.addWidget(severity)
        badges.addWidget(category)
        badges.addWidget(status)
        badges.addStretch()
        layout.addLayout(badges)

        section = QLabel(comment.get("section") or "Awal Dokumen")
        section.setStyleSheet("font-weight: 600; color: #555;")
        section.setWordWrap(True)
        layout.addWidget(section)

        selected = (comment.get("selected_text") or "").strip()
        if selected:
            quote = QLabel(
                f'“{selected[:220]}{"…" if len(selected) > 220 else ""}”'
            )
            quote.setWordWrap(True)
            quote.setStyleSheet(
                "background: #fafafa; padding: 7px; color: #666; "
                "font-style: italic;"
            )
            layout.addWidget(quote)

        body = QLabel(comment.get("content") or "")
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(body)

        timestamp = QLabel(comment.get("created_at") or "")
        timestamp.setStyleSheet("color: #999; font-size: 10px;")
        layout.addWidget(timestamp)

        actions = QHBoxLayout()

        goto_button = QPushButton("Ke paragraf")
        goto_button.clicked.connect(
            lambda: self.goto_requested.emit(self.comment_id)
        )
        actions.addWidget(goto_button)

        edit_button = QPushButton("Edit")
        edit_button.clicked.connect(
            lambda: self.edit_requested.emit(self.comment_id)
        )
        actions.addWidget(edit_button)

        toggle_text = (
            "Buka Lagi"
            if comment.get("status") == "Resolved"
            else "Selesai"
        )
        toggle_button = QPushButton(toggle_text)
        toggle_button.clicked.connect(
            lambda: self.toggle_requested.emit(self.comment_id)
        )
        actions.addWidget(toggle_button)

        delete_button = QPushButton("Hapus")
        delete_button.clicked.connect(
            lambda: self.delete_requested.emit(self.comment_id)
        )
        actions.addWidget(delete_button)

        layout.addLayout(actions)


class ReviewPage(QWidget):
    def __init__(self):
        super().__init__()

        self.current_document_id: int | None = None
        self.current_file_path: Path | None = None
        self.current_paragraphs: list[dict] = []
        self.paragraph_widgets: dict[int, PreviewParagraphOverlay] = {}
        self.highlighted_paragraph_index: int | None = None
        self._loading = False

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(14)

        header = QHBoxLayout()
        title_box = QVBoxLayout()

        title = QLabel("Review Dokumen")
        title.setStyleSheet("font-size: 26px; font-weight: 700;")
        subtitle = QLabel(
            "Pilih paragraf atau blok teks, lalu berikan catatan koreksi."
        )
        subtitle.setStyleSheet("color: #666;")

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
        self.thesis_combo.setMinimumWidth(300)
        self.thesis_combo.currentIndexChanged.connect(self.load_documents)
        toolbar.addWidget(self.thesis_combo, 2)

        toolbar.addWidget(QLabel("Dokumen"))
        self.document_combo = QComboBox()
        self.document_combo.setMinimumWidth(220)
        self.document_combo.currentIndexChanged.connect(self.load_document)
        toolbar.addWidget(self.document_combo, 1)

        self.open_button = QPushButton("Buka File Asli")
        self.open_button.clicked.connect(self.open_original_file)
        toolbar.addWidget(self.open_button)

        root.addLayout(toolbar)

        self.version_info = QLabel("Pilih skripsi untuk mulai review.")
        self.version_info.setStyleSheet("color: #777; font-size: 12px;")
        self.version_info.setWordWrap(True)
        root.addWidget(self.version_info)

        splitter = QSplitter(Qt.Horizontal)
        root.addWidget(splitter, 1)

        splitter.addWidget(self.build_structure_panel())
        splitter.addWidget(self.build_document_panel())
        splitter.addWidget(self.build_comments_panel())
        splitter.setSizes([230, 700, 360])

        self.update_actions()

    def build_structure_panel(self) -> QWidget:
        panel = QFrame()
        panel.setFrameShape(QFrame.StyledPanel)
        panel.setStyleSheet(
            "QFrame { background: #ffffff; border: 1px solid #d9d9d9; }"
            "QLabel { border: none; color: #111111; }"
        )

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)

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
            "QTreeWidget::item {"
            " padding: 5px 3px;"
            " border-radius: 4px;"
            "}"
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
        if item.childCount():
            prefix = "−  " if item.isExpanded() else "+  "
        else:
            prefix = "   "
        item.setText(0, f"{prefix}{label}")

    def build_document_panel(self) -> QWidget:
        panel = QFrame()
        panel.setFrameShape(QFrame.NoFrame)
        panel.setStyleSheet("background: #d9d9d9;")

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        self.document_scroll = QScrollArea()
        self.document_scroll.setWidgetResizable(True)
        self.document_scroll.setFrameShape(QFrame.NoFrame)
        self.document_scroll.setStyleSheet(
            "QScrollArea { background: #d9d9d9; border: none; }"
            "QScrollBar:vertical { width: 12px; }"
        )

        self.document_workspace = QWidget()
        self.document_workspace.setStyleSheet("background: #d9d9d9;")

        self.document_layout = QVBoxLayout(self.document_workspace)
        self.document_layout.setContentsMargins(26, 28, 26, 42)
        self.document_layout.setSpacing(22)
        self.document_layout.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self.document_layout.addStretch()

        self.document_scroll.setWidget(self.document_workspace)
        layout.addWidget(self.document_scroll)

        return panel

    def build_comments_panel(self) -> QWidget:
        panel = QFrame()
        panel.setFrameShape(QFrame.StyledPanel)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel("CATATAN REVIEW")
        title.setStyleSheet("font-weight: 700;")
        header.addWidget(title)
        header.addStretch()

        self.comment_filter = QComboBox()
        self.comment_filter.addItems(["Aktif", "Semua", "Selesai"])
        self.comment_filter.currentTextChanged.connect(self.load_comments)
        header.addWidget(self.comment_filter)

        layout.addLayout(header)

        self.comment_count = QLabel("0 komentar")
        self.comment_count.setStyleSheet("color: #777; font-size: 11px;")
        layout.addWidget(self.comment_count)

        self.comments_scroll = QScrollArea()
        self.comments_scroll.setWidgetResizable(True)
        self.comments_scroll.setFrameShape(QFrame.NoFrame)

        self.comments_container = QWidget()
        self.comments_layout = QVBoxLayout(self.comments_container)
        self.comments_layout.setContentsMargins(0, 0, 0, 0)
        self.comments_layout.setSpacing(8)
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
        self.paragraph_widgets = {}
        self.highlighted_paragraph_index = None

        self.clear_layout(self.document_layout)
        self.clear_structure()

        if self.current_document_id is None:
            self.version_info.setText(
                "Skripsi ini belum mempunyai dokumen untuk direview."
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

                document_meta = {
                    "version": document.version,
                    "kind": document.kind,
                    "uploaded_at": document.uploaded_at,
                    "student": document.thesis.student.name,
                }

            paragraphs = extract_review_paragraphs(file_path)
            structure = extract_review_structure(
                file_path,
                paragraphs=paragraphs,
            )

            preview_pdf = ensure_preview_pdf(file_path)
            preview_pages = render_preview_pages(
                preview_pdf,
                dpi=120,
            )
            anchors = map_review_paragraphs_to_preview(
                file_path,
                preview_pdf,
                paragraphs=paragraphs,
            )

            self.current_file_path = file_path
            self.current_paragraphs = paragraphs

            comment_counts = self.comment_counts_by_paragraph()

            anchors_by_page: dict[int, list[dict]] = {}
            for anchor in anchors:
                anchors_by_page.setdefault(
                    int(anchor["page_index"]),
                    [],
                ).append(anchor)

            for page_data in preview_pages:
                page_index = int(page_data["page_index"])

                page_widget = PreviewPageWidget(
                    page_data=page_data,
                    anchors=anchors_by_page.get(page_index, []),
                    comment_counts=comment_counts,
                )
                page_widget.comment_requested.connect(
                    self.add_comment_for_paragraph
                )

                self.document_layout.insertWidget(
                    self.document_layout.count() - 1,
                    page_widget,
                    0,
                    Qt.AlignHCenter,
                )
                self.paragraph_widgets.update(
                    page_widget.overlay_widgets
                )

            self.populate_structure(structure)

            kind = DOCUMENT_KIND_LABELS.get(
                document_meta["kind"],
                document_meta["kind"].title(),
            )
            self.version_info.setText(
                f'{document_meta["student"]}  •  '
                f'V{document_meta["version"]} {kind}  •  '
                f'{document_meta["uploaded_at"].strftime("%d-%m-%Y %H:%M")}  •  '
                f'{file_path.name}  •  '
                f'{len(preview_pages)} halaman'
            )

        except Exception as exc:
            self.version_info.setText(
                f"Dokumen tidak dapat dirender: {exc}"
            )

        self.load_comments()
        self.update_actions()

    def clear_layout(self, layout: QVBoxLayout) -> None:
        while layout.count() > 1:
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

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
        widget = self.paragraph_widgets.get(paragraph_index)
        if widget is None:
            return

        if (
            self.highlighted_paragraph_index is not None
            and self.highlighted_paragraph_index in self.paragraph_widgets
        ):
            self.paragraph_widgets[
                self.highlighted_paragraph_index
            ].set_highlighted(False)

        self.highlighted_paragraph_index = paragraph_index
        widget.set_highlighted(True)

        self.document_scroll.ensureWidgetVisible(widget, 30, 45)

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

        dialog = CommentDialog(
            paragraph_text=paragraph["text"],
            selected_text=selected_text,
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
                    selected_text=payload["selected_text"] or selected_text,
                    category=payload["category"],
                    severity=payload["severity"],
                    content=payload["content"],
                    status="Open",
                )
            )
            session.commit()

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

    def load_comments(self, *_args) -> None:
        self.clear_layout(self.comments_layout)

        if self.current_document_id is None:
            self.comment_count.setText("0 komentar")
            self.update_actions()
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
            f"{active_count} aktif • {len(rows)} tampil"
        )

        if not rows:
            empty = QLabel(
                "Belum ada komentar.\nPilih paragraf lalu klik Komentar."
            )
            empty.setAlignment(Qt.AlignCenter)
            empty.setWordWrap(True)
            empty.setStyleSheet("color: #888; padding: 24px;")
            self.comments_layout.insertWidget(
                self.comments_layout.count() - 1,
                empty,
            )
            self.update_actions()
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

        self.update_actions()

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

            data = {
                "category": comment.category,
                "severity": comment.severity,
                "content": comment.content,
            }
            paragraph_index = comment.paragraph_index
            selected_text = comment.selected_text or ""
            section = comment.section or "Awal Dokumen"

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
        with SessionLocal() as session:
            comment = session.get(ReviewComment, comment_id)
            if comment is None:
                return

            comment.status = (
                "Resolved"
                if comment.status != "Resolved"
                else "Open"
            )
            session.commit()

        self.load_document()

    def delete_comment(self, comment_id: int) -> None:
        with SessionLocal() as session:
            comment = session.get(ReviewComment, comment_id)
            if comment is None:
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

        self.load_document()

    def open_original_file(self) -> None:
        if not self.current_file_path or not self.current_file_path.exists():
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
                (
                    "Komentar Word native hanya tersedia untuk sumber DOCX. "
                    "Untuk PDF, komentar tetap tersimpan di aplikasi."
                ),
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

        default_name = (
            self.current_file_path.stem + "_koreksi.docx"
        )
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
                f"{output_path}\n\n"
                "File ini dapat langsung dikembalikan ke mahasiswa."
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
