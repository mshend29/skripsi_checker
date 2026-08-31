from __future__ import annotations

import re
import shutil
from pathlib import Path

import pymupdf
from docx import Document as DocxDocument


BASE_DIR = Path(__file__).resolve().parents[2]
STORAGE_DIR = BASE_DIR / "storage"

DOCUMENT_FOLDERS = {
    "proposal": STORAGE_DIR / "proposals",
    "revision": STORAGE_DIR / "revisions",
    "final": STORAGE_DIR / "finals",
}


def extract_text(file_path: str | Path) -> str:
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix == ".docx":
        document = DocxDocument(path)
        return "\n".join(p.text for p in document.paragraphs if p.text.strip())

    if suffix == ".pdf":
        with pymupdf.open(path) as document:
            return "\n".join(page.get_text("text") for page in document)

    raise ValueError("Format dokumen belum didukung. Gunakan DOCX atau PDF.")


def extract_sections(text: str) -> list[str]:
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    sections: list[str] = []
    seen: set[str] = set()

    patterns = [
        re.compile(r"^BAB\s+[IVXLCDM]+(?:\s*[-.:]?\s*.*)?$", re.IGNORECASE),
        re.compile(r"^\d+(?:\.\d+){1,3}\s+.+$"),
    ]

    for line in lines:
        if not line or len(line) > 180:
            continue

        is_heading = any(pattern.match(line) for pattern in patterns)

        if not is_heading:
            words = line.split()
            if 1 < len(words) <= 10 and len(line) <= 100:
                letters = [char for char in line if char.isalpha()]
                if letters and line.upper() == line:
                    is_heading = True

        if not is_heading:
            continue

        key = line.casefold()
        if key in seen:
            continue

        seen.add(key)
        sections.append(line)

        if len(sections) >= 150:
            break

    return sections


def detect_title(text: str) -> str:
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    lines = [line for line in lines if line]

    candidates: list[str] = []
    ignored = {
        "proposal",
        "proposal skripsi",
        "skripsi",
        "tugas akhir",
        "bab i",
        "pendahuluan",
    }

    for line in lines[:50]:
        normalized = line.casefold()
        if normalized in ignored:
            continue
        if normalized.startswith("bab i"):
            break
        if 15 <= len(line) <= 220:
            candidates.append(line)

    if not candidates:
        return ""

    return max(candidates, key=len)


def resolve_storage_path(file_path: str | Path) -> Path:
    path = Path(file_path)
    if path.is_absolute():
        return path
    return BASE_DIR / path


def store_document(
    thesis_id: int,
    source_path: str | Path,
    version: int,
    kind: str,
) -> tuple[str, str]:
    if kind not in DOCUMENT_FOLDERS:
        raise ValueError("Jenis dokumen tidak dikenali.")

    source = Path(source_path)
    if not source.is_file():
        raise ValueError("File sumber tidak ditemukan.")

    if source.suffix.lower() not in {".docx", ".pdf"}:
        raise ValueError("Dokumen harus berupa file DOCX atau PDF.")

    target_dir = DOCUMENT_FOLDERS[kind] / str(thesis_id)
    target_dir.mkdir(parents=True, exist_ok=True)

    safe_name = re.sub(r"[^A-Za-z0-9._ -]", "_", source.name)
    target = target_dir / f"v{version}_{safe_name}"

    if target.exists():
        counter = 2
        while target.exists():
            target = target_dir / f"v{version}_{counter}_{safe_name}"
            counter += 1

    shutil.copy2(source, target)

    text = extract_text(target)
    detected_title = detect_title(text)

    relative_path = target.relative_to(BASE_DIR).as_posix()
    return relative_path, detected_title


def import_proposal(
    thesis_id: int,
    source_path: str | Path,
    version: int,
) -> tuple[str, str]:
    return store_document(
        thesis_id=thesis_id,
        source_path=source_path,
        version=version,
        kind="proposal",
    )



def _heading_label(text: str, style_name: str = "") -> bool:
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return False

    if style_name.lower().startswith("heading"):
        return True

    patterns = [
        re.compile(r"^BAB\s+[IVXLCDM]+(?:\s*[-.:]?\s*.*)?$", re.IGNORECASE),
        re.compile(r"^\d+(?:\.\d+){1,3}\s+.+$"),
    ]
    if any(pattern.match(normalized) for pattern in patterns):
        return True

    words = normalized.split()
    letters = [char for char in normalized if char.isalpha()]
    return bool(
        1 < len(words) <= 10
        and len(normalized) <= 100
        and letters
        and normalized.upper() == normalized
    )


def extract_review_paragraphs(file_path: str | Path) -> list[dict]:
    path = Path(file_path)
    suffix = path.suffix.lower()
    result: list[dict] = []
    current_section = "Awal Dokumen"

    if suffix == ".docx":
        document = DocxDocument(path)
        for source_index, paragraph in enumerate(document.paragraphs):
            text_value = re.sub(r"\s+", " ", paragraph.text).strip()
            if not text_value:
                continue

            style_name = paragraph.style.name if paragraph.style else ""
            is_heading = _heading_label(text_value, style_name)

            if is_heading:
                current_section = text_value

            result.append(
                {
                    "paragraph_index": source_index,
                    "display_index": len(result) + 1,
                    "text": text_value,
                    "section": current_section,
                    "style_name": style_name,
                    "is_heading": is_heading,
                }
            )

        return result

    if suffix == ".pdf":
        with pymupdf.open(path) as document:
            source_index = 0
            for page_number, page in enumerate(document, start=1):
                blocks = page.get_text("blocks")
                for block in blocks:
                    text_value = re.sub(r"\s+", " ", block[4]).strip()
                    if not text_value:
                        continue

                    is_heading = _heading_label(text_value)
                    if is_heading:
                        current_section = text_value

                    result.append(
                        {
                            "paragraph_index": source_index,
                            "display_index": len(result) + 1,
                            "text": text_value,
                            "section": current_section,
                            "style_name": f"PDF halaman {page_number}",
                            "is_heading": is_heading,
                        }
                    )
                    source_index += 1

        return result

    raise ValueError("Format dokumen belum didukung. Gunakan DOCX atau PDF.")


def export_docx_with_comments(
    source_path: str | Path,
    output_path: str | Path,
    comments: list[dict],
    author: str = "Dosen Pembimbing",
    initials: str = "DP",
) -> int:
    source = Path(source_path)
    target = Path(output_path)

    if source.suffix.lower() != ".docx":
        raise ValueError(
            "Komentar Word hanya dapat ditanamkan ke dokumen DOCX."
        )

    document = DocxDocument(source)
    exported = 0

    for item in comments:
        paragraph_index = item.get("paragraph_index")
        if paragraph_index is None:
            continue

        if not 0 <= int(paragraph_index) < len(document.paragraphs):
            continue

        paragraph = document.paragraphs[int(paragraph_index)]
        runs = list(paragraph.runs)

        if not runs:
            runs = [paragraph.add_run("")]

        category = item.get("category") or "Umum"
        severity = item.get("severity") or "Moderate"
        selected_text = (item.get("selected_text") or "").strip()
        comment_text = (item.get("content") or "").strip()

        parts = [
            f"[{severity}] [{category}]",
        ]
        if selected_text and selected_text != paragraph.text.strip():
            parts.append(f'Kutipan: "{selected_text}"')
        parts.append(comment_text)

        document.add_comment(
            runs=runs,
            text="\n".join(parts),
            author=author,
            initials=initials,
        )
        exported += 1

    target.parent.mkdir(parents=True, exist_ok=True)
    document.save(target)
    return exported
