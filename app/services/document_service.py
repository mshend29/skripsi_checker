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
