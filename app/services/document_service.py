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

MAJOR_SECTION_NAMES = {
    "ABSTRAK",
    "ABSTRACT",
    "DAFTAR PUSTAKA",
    "REFERENCES",
    "LAMPIRAN",
    "APPENDIX",
}


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def extract_text(file_path: str | Path) -> str:
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix == ".docx":
        document = DocxDocument(path)
        return "\n".join(
            paragraph.text
            for paragraph in document.paragraphs
            if paragraph.text.strip()
        )

    if suffix == ".pdf":
        with pymupdf.open(path) as document:
            return "\n".join(page.get_text("text") for page in document)

    raise ValueError("Format dokumen belum didukung. Gunakan DOCX atau PDF.")


def extract_sections(text: str) -> list[str]:
    lines = [_normalize_text(line) for line in text.splitlines()]
    sections: list[str] = []
    seen: set[str] = set()

    for line in lines:
        if not line or len(line) > 180:
            continue
        if not _heading_label(line):
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
    lines = [_normalize_text(line) for line in text.splitlines()]
    lines = [line for line in lines if line]

    candidates: list[str] = []
    ignored = {
        "proposal",
        "proposal skripsi",
        "skripsi",
        "tugas akhir",
        "bab i",
        "pendahuluan",
        "daftar isi",
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
    normalized = _normalize_text(text)
    if not normalized:
        return False

    style_lower = style_name.lower()
    if style_lower.startswith("heading"):
        return True

    patterns = [
        re.compile(
            r"^BAB\s+(?:[IVXLCDM]+|\d+)(?:\s*[-.:]?\s*.*)?$",
            re.IGNORECASE,
        ),
        re.compile(r"^\d+(?:\.\d+){1,3}\s+.+$"),
    ]
    if any(pattern.match(normalized) for pattern in patterns):
        return True

    return normalized.upper() in MAJOR_SECTION_NAMES


def _chapter_key(text: str) -> str | None:
    normalized = _normalize_text(text)
    match = re.match(
        r"^(BAB\s+(?:[IVXLCDM]+|\d+))\b",
        normalized,
        re.IGNORECASE,
    )
    if match:
        return match.group(1).upper()
    return None


def _numbering_key(text: str) -> str | None:
    normalized = _normalize_text(text)
    match = re.match(r"^(\d+(?:\.\d+){1,3})\b", normalized)
    return match.group(1) if match else None


def _structure_level(text: str, style_name: str = "") -> int:
    style_match = re.search(r"(\d+)", style_name or "")
    if style_name.lower().startswith("toc") and style_match:
        return max(1, min(4, int(style_match.group(1))))

    if _chapter_key(text):
        return 1

    numbering = _numbering_key(text)
    if numbering:
        return min(4, numbering.count(".") + 1)

    return 1


def _looks_like_toc_entry(raw_text: str, style_name: str = "") -> bool:
    stripped = (raw_text or "").strip()
    if not stripped:
        return False

    if style_name.lower().startswith("toc"):
        return True

    if "\t" in stripped:
        return True

    if re.search(r"\.{3,}\s*(?:\d+|[ivxlcdm]+)\s*$", stripped, re.I):
        return True

    if (
        (_chapter_key(stripped) or _numbering_key(stripped))
        and re.search(r"\s+(?:\d+|[ivxlcdm]+)\s*$", stripped, re.I)
    ):
        return True

    return False


def _clean_toc_entry(raw_text: str) -> str:
    value = (raw_text or "").replace("\xa0", " ").strip()
    value = re.sub(
        r"\s*(?:\.{2,}|\t+)\s*(?:\d+|[ivxlcdm]+)\s*$",
        "",
        value,
        flags=re.IGNORECASE,
    )
    value = re.sub(
        r"(?<=\D)\s{2,}(?:\d+|[ivxlcdm]+)\s*$",
        "",
        value,
        flags=re.IGNORECASE,
    )
    return _normalize_text(value)


def _find_toc_bounds(rows: list[dict]) -> tuple[int | None, int | None]:
    toc_start: int | None = None

    for position, row in enumerate(rows):
        if row["text"].casefold() == "daftar isi":
            toc_start = position
            break

    if toc_start is None:
        return None, None

    toc_end = toc_start
    saw_entry = False

    for position in range(toc_start + 1, len(rows)):
        row = rows[position]
        raw_text = row.get("raw_text") or row["text"]
        style_name = row.get("style_name") or ""

        if _looks_like_toc_entry(raw_text, style_name):
            saw_entry = True
            toc_end = position
            continue

        if not saw_entry:
            if position - toc_start <= 3:
                toc_end = position
                continue
            break

        if _chapter_key(row["text"]) or (
            style_name.lower().startswith("heading")
            and not style_name.lower().startswith("toc")
        ):
            break

        if position - toc_end <= 2 and len(row["text"]) < 120:
            toc_end = position
            continue

        break

    return toc_start, toc_end


def _match_structure_target(
    label: str,
    rows: list[dict],
    start_position: int,
) -> int | None:
    chapter_key = _chapter_key(label)
    numbering_key = _numbering_key(label)
    normalized_label = _normalize_text(label).casefold()

    for row in rows[start_position:]:
        text = row["text"]
        text_lower = text.casefold()

        if chapter_key and _chapter_key(text) == chapter_key:
            return int(row["paragraph_index"])

        if numbering_key and _numbering_key(text) == numbering_key:
            return int(row["paragraph_index"])

        if normalized_label == text_lower:
            return int(row["paragraph_index"])

        if len(normalized_label) > 8 and (
            normalized_label in text_lower or text_lower in normalized_label
        ):
            return int(row["paragraph_index"])

    return None


def _build_tree(entries: list[dict]) -> list[dict]:
    roots: list[dict] = []
    stack: list[tuple[int, dict]] = []

    for entry in entries:
        node = {
            "label": entry["label"],
            "paragraph_index": entry.get("paragraph_index"),
            "children": [],
        }
        level = max(1, int(entry.get("level", 1)))

        while stack and stack[-1][0] >= level:
            stack.pop()

        if stack:
            stack[-1][1]["children"].append(node)
        else:
            roots.append(node)

        stack.append((level, node))

    return roots


def extract_review_paragraphs(file_path: str | Path) -> list[dict]:
    path = Path(file_path)
    suffix = path.suffix.lower()
    rows: list[dict] = []

    if suffix == ".docx":
        document = DocxDocument(path)
        for source_index, paragraph in enumerate(document.paragraphs):
            raw_text = paragraph.text.strip()
            text_value = _normalize_text(raw_text)
            if not text_value:
                continue

            style_name = paragraph.style.name if paragraph.style else ""
            rows.append(
                {
                    "paragraph_index": source_index,
                    "display_index": len(rows) + 1,
                    "text": text_value,
                    "raw_text": raw_text,
                    "section": "Halaman Awal / Halaman Judul",
                    "style_name": style_name,
                    "is_heading": _heading_label(text_value, style_name),
                }
            )

    elif suffix == ".pdf":
        with pymupdf.open(path) as document:
            source_index = 0
            for page_number, page in enumerate(document, start=1):
                blocks = page.get_text("blocks")
                for block in blocks:
                    raw_text = str(block[4]).strip()
                    text_value = _normalize_text(raw_text)
                    if not text_value:
                        continue

                    rows.append(
                        {
                            "paragraph_index": source_index,
                            "display_index": len(rows) + 1,
                            "text": text_value,
                            "raw_text": raw_text,
                            "section": "Halaman Awal / Halaman Judul",
                            "style_name": f"PDF halaman {page_number}",
                            "is_heading": _heading_label(text_value),
                        }
                    )
                    source_index += 1
    else:
        raise ValueError(
            "Format dokumen belum didukung. Gunakan DOCX atau PDF."
        )

    toc_start, toc_end = _find_toc_bounds(rows)
    current_section = "Halaman Awal / Halaman Judul"

    for position, row in enumerate(rows):
        if toc_start is not None and toc_end is not None:
            if toc_start <= position <= toc_end:
                row["section"] = "Daftar Isi"
                continue
            if position < toc_start:
                row["section"] = "Halaman Awal / Halaman Judul"
                continue

        if row["is_heading"]:
            current_section = row["text"]

        row["section"] = current_section

    return rows


def extract_review_structure(
    file_path: str | Path,
    paragraphs: list[dict] | None = None,
) -> list[dict]:
    rows = paragraphs or extract_review_paragraphs(file_path)
    if not rows:
        return []

    roots: list[dict] = [
        {
            "label": "Halaman Awal / Halaman Judul",
            "paragraph_index": int(rows[0]["paragraph_index"]),
            "children": [],
        }
    ]

    toc_start, toc_end = _find_toc_bounds(rows)
    entries: list[dict] = []

    if toc_start is not None and toc_end is not None:
        roots.append(
            {
                "label": "Daftar Isi",
                "paragraph_index": int(rows[toc_start]["paragraph_index"]),
                "children": [],
            }
        )

        search_start = min(len(rows), toc_end + 1)

        for row in rows[toc_start + 1 : toc_end + 1]:
            raw_text = row.get("raw_text") or row["text"]
            style_name = row.get("style_name") or ""
            if not _looks_like_toc_entry(raw_text, style_name):
                continue

            label = _clean_toc_entry(raw_text)
            if not label:
                continue

            label_folded = label.casefold()
            if label_folded in {
                "daftar isi",
                "halaman awal",
                "halaman judul",
            }:
                continue

            if not (
                _chapter_key(label)
                or _numbering_key(label)
                or label.upper() in MAJOR_SECTION_NAMES
            ):
                continue

            entries.append(
                {
                    "label": label,
                    "level": _structure_level(label, style_name),
                    "paragraph_index": _match_structure_target(
                        label,
                        rows,
                        search_start,
                    ),
                }
            )

        if entries:
            roots.extend(_build_tree(entries))
            return roots

    fallback_entries: list[dict] = []
    start_position = (toc_end + 1) if toc_end is not None else 0

    for row in rows[start_position:]:
        label = row["text"]
        if label.casefold() == "daftar isi":
            if not any(root["label"] == "Daftar Isi" for root in roots):
                roots.append(
                    {
                        "label": "Daftar Isi",
                        "paragraph_index": int(row["paragraph_index"]),
                        "children": [],
                    }
                )
            continue

        if not (
            _chapter_key(label)
            or _numbering_key(label)
            or label.upper() in MAJOR_SECTION_NAMES
        ):
            continue

        fallback_entries.append(
            {
                "label": label,
                "level": _structure_level(
                    label,
                    row.get("style_name") or "",
                ),
                "paragraph_index": int(row["paragraph_index"]),
            }
        )

    roots.extend(_build_tree(fallback_entries))
    return roots


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

        parts = [f"[{severity}] [{category}]"]
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
