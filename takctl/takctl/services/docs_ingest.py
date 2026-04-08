from __future__ import annotations

import hashlib
import json
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from takctl.config import load_config
from takctl.services.docs_paths import (
    ensure_docs_dirs,
    raw_doc_dir,
    raw_original_path,
    derived_doc_dir,
    manifest_path,
    status_path,
    extract_path,
    sections_path,
    chunks_path,
    errors_path,
)
from takctl.services.docs_registry import upsert_doc


def iso_z(dt: datetime | None = None) -> str:
    dt = dt or datetime.now(timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def make_doc_id() -> str:
    return f"doc-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def write_manifest(doc_id: str, manifest: dict[str, Any]) -> None:
    _write_json(manifest_path(doc_id), manifest)


def write_status(doc_id: str, *, status: str, steps: dict[str, Any] | None = None, error: str = "") -> None:
    _write_json(
        status_path(doc_id),
        {
            "status": status,
            "updated_at": iso_z(),
            "steps": steps or {},
            "error": error,
        },
    )


def initialize_sections_placeholder(doc_id: str, title: str) -> None:
    _write_json(
        sections_path(doc_id),
        {
            "doc_id": doc_id,
            "title": title,
            "items": [],
        },
    )


def _normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _ocr_lang_from_config() -> str:
    cfg = load_config()

    raw = ""
    for key in (
        "docs_lang",
        "docs_language",
        "ocr_lang",
        "ocr_language",
        "language",
        "lang",
    ):
        v = str(cfg.get(key, "") or "").strip()
        if v:
            raw = v
            break

    code = (raw or "EN").upper()
    if code == "SV":
        return "swe"
    if code == "EN":
        return "eng"
    raise RuntimeError(f"unsupported OCR language in config: {raw!r} (expected SV or EN)")


def _pdf_page_count(pdf_path: Path) -> int | None:
    try:
        from pypdf import PdfReader  # type: ignore
        return len(PdfReader(str(pdf_path)).pages)
    except Exception:
        pass

    try:
        import subprocess
        out = subprocess.run(
            ["pdfinfo", str(pdf_path)],
            text=True,
            capture_output=True,
            check=False,
        )
        if out.returncode == 0:
            m = re.search(r"^Pages:\s+(\d+)\s*$", out.stdout or "", re.MULTILINE)
            if m:
                return int(m.group(1))
    except Exception:
        pass

    return None


def _validate_extracted_text(pdf_path: Path, text: str) -> str:
    text = _normalize_text(text)
    text_len = len(text)
    pages = _pdf_page_count(pdf_path)

    if text_len < 400:
        raise RuntimeError("could not extract enough text from PDF (very small extract)")

    if pages and pages >= 40:
        chars_per_page = text_len / max(pages, 1)
        if text_len < 5000 or chars_per_page < 80:
            raise RuntimeError(
                f"extracted text too small for PDF ({text_len} chars across {pages} pages; likely scanned/image PDF requiring OCR)"
            )

    return text


def _extract_pdf_text_basic(pdf_path: Path) -> str:
    try:
        from pypdf import PdfReader  # type: ignore
        reader = PdfReader(str(pdf_path))
        parts: list[str] = []
        for page in reader.pages:
            try:
                t = page.extract_text() or ""
            except Exception:
                t = ""
            if t.strip():
                parts.append(t.strip())
        text = "\n\n".join(parts).strip()
        if text:
            return _normalize_text(text)
    except Exception:
        pass

    try:
        import subprocess
        out = subprocess.run(
            ["pdftotext", "-layout", str(pdf_path), "-"],
            text=True,
            capture_output=True,
            check=False,
        )
        if out.returncode == 0 and (out.stdout or "").strip():
            return _normalize_text(out.stdout)
    except Exception:
        pass

    raise RuntimeError("could not extract text from PDF (no usable parser output)")


def _ocr_pdf_to_text(pdf_path: Path) -> str:
    import subprocess
    import tempfile

    with tempfile.TemporaryDirectory(prefix="taks-ocr-") as td:
        td_path = Path(td)
        ocr_pdf = td_path / "ocr.pdf"

        out = subprocess.run(
            [
                "ocrmypdf",
                "--quiet",
                "--skip-big",
                "50",
                "--language",
                _ocr_lang_from_config(),
                "--force-ocr",
                str(pdf_path),
                str(ocr_pdf),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        if out.returncode != 0:
            detail = (out.stderr or out.stdout or "").strip()
            raise RuntimeError(f"OCR failed: {detail or 'ocrmypdf returned non-zero exit code'}")

        out2 = subprocess.run(
            ["pdftotext", "-layout", str(ocr_pdf), "-"],
            text=True,
            capture_output=True,
            check=False,
        )
        if out2.returncode == 0 and (out2.stdout or "").strip():
            return _normalize_text(out2.stdout)

        raise RuntimeError("OCR completed but no usable text was extracted from OCR PDF")


def extract_pdf_text(pdf_path: Path) -> tuple[str, str]:
    try:
        basic = _extract_pdf_text_basic(pdf_path)
        return _validate_extracted_text(pdf_path, basic), "basic"
    except Exception:
        ocr_text = _ocr_pdf_to_text(pdf_path)
        return _validate_extracted_text(pdf_path, ocr_text), "ocr_fallback"


def _chunk_text(text: str, *, chunk_chars: int = 1800, overlap_chars: int = 250) -> list[str]:
    s = _normalize_text(text)
    if not s:
        return []
    chunks: list[str] = []
    start = 0
    n = len(s)
    while start < n:
        end = min(n, start + chunk_chars)
        chunk = s[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= n:
            break
        start = max(end - overlap_chars, start + 1)
    return chunks



_HEADING_RE = re.compile(
    r"^\s*(\d+(?:\.\d+){0,3})\.\s+([A-ZÅÄÖA-Za-z][^\n]{1,140})\s*$",
    re.MULTILINE,
)


def _clean_heading_title(title: str) -> str:
    t = str(title or "").strip()
    t = re.sub(r"\s{2,}", " ", t)
    t = re.sub(r"\.{3,}.*$", "", t).strip()
    t = re.sub(r"\s+\d+\s*$", "", t).strip()
    return t


def _looks_like_toc_title(title: str) -> bool:
    t = str(title or "")
    return (
        "..." in t
        or "….." in t
        or "................................................................" in t
    )


def _line_bounds(text: str, pos: int) -> tuple[int, int]:
    a = text.rfind("\n", 0, pos)
    b = text.find("\n", pos)
    if a < 0:
        a = 0
    else:
        a += 1
    if b < 0:
        b = len(text)
    return a, b


def _candidate_score(text: str, m: re.Match[str]) -> int:
    num = str(m.group(1) or "").strip()
    title = _clean_heading_title(m.group(2) or "")
    start = m.start()

    line_a, line_b = _line_bounds(text, start)
    line = text[line_a:line_b]
    prev_a, prev_b = _line_bounds(text, max(0, line_a - 2))
    prev_line = text[prev_a:prev_b].strip()
    next_a, next_b = _line_bounds(text, min(len(text) - 1, line_b + 1 if line_b < len(text) else line_b))
    next_line = text[next_a:next_b].strip()

    score = 0

    # Hard rejects
    if not title:
        return -999
    if num.startswith("0"):
        return -999
    if len(title) < 2:
        return -999
    if any(x in title for x in ['"', "'", '”']) and len(title) < 12:
        return -999
    if re.search(r'[^A-Za-zÅÄÖåäö0-9 ()/,\-]', title):
        score -= 25

    # Heading-like shape
    score += 20
    if len(title) <= 80:
        score += 10
    if title[:1].isupper():
        score += 5
    if re.fullmatch(r"[A-ZÅÄÖ0-9 ()/\-]{4,}", title or ""):
        score += 8
    if re.fullmatch(r"[A-Za-zÅÄÖåäö0-9 ()/\-]{4,}", title or ""):
        score += 6

    # TOC penalties
    if _looks_like_toc_title(line):
        score -= 120
    if re.search(r"\.{5,}\s*\d+\s*$", line):
        score -= 120
    if re.search(r"\b(INNEHÅLL|CONTENTS)\b", prev_line, re.IGNORECASE):
        score -= 80

    # Early-frontmatter penalty, but not fatal
    if start < max(5000, len(text) // 40):
        score -= 25

    # Inline / paragraph penalties
    if prev_line and prev_line[-1:] not in {"", ".", "!", "?", ":"}:
        score -= 20
    if next_line and len(next_line) > 180:
        score -= 10
    if prev_line and len(prev_line) > 120:
        score -= 10

    # Real heading bonuses
    if not prev_line:
        score += 10
    if next_line and len(next_line) > 0:
        score += 8
    if next_line and not re.match(r"^\d+(?:\.\d+){0,3}\.\s", next_line):
        score += 10

    # Prefer more specific numbering
    score += num.count(".") * 3

    return score


def _parse_sections_from_text(text: str) -> list[dict[str, Any]]:
    src = str(text or "")
    if not src.strip():
        return []

    matches = list(_HEADING_RE.finditer(src))
    if not matches:
        return []

    by_num: dict[str, tuple[int, re.Match[str], str]] = {}

    for m in matches:
        num = str(m.group(1) or "").strip()
        title = _clean_heading_title(m.group(2) or "")
        if not num or not title:
            continue

        score = _candidate_score(src, m)
        cur = by_num.get(num)
        if cur is None or score > cur[0] or (score == cur[0] and m.start() > cur[1].start()):
            by_num[num] = (score, m, title)

    picked: list[tuple[int, re.Match[str], str]] = []
    for num, item in by_num.items():
        score, m, title = item
        if score < 0:
            continue
        picked.append((score, m, title))

    picked.sort(key=lambda x: x[1].start())

    raw_items: list[dict[str, Any]] = []
    for i, (score, m, title) in enumerate(picked):
        num = str(m.group(1) or "").strip()
        start = m.start()
        end = picked[i + 1][1].start() if i + 1 < len(picked) else len(src)
        level = num.count(".") + 1
        raw_items.append({
            "id": num,
            "title": title,
            "level": level,
            "score": score,
            "start_offset": start,
            "end_offset": end,
        })

    # Find the first stable sequence start.
    # Heuristic: prefer the earliest place where we soon get several headings
    # starting with 1.x / 2.x rather than isolated later-number fragments.
    start_idx = 0
    for i, item in enumerate(raw_items):
        nums = [str(x.get("id") or "") for x in raw_items[i:i+8]]
        score = 0
        for n in nums:
            if n == "1" or n.startswith("1."):
                score += 3
            elif n == "2" or n.startswith("2."):
                score += 2
            elif n == "3" or n.startswith("3."):
                score += 1
        if score >= 10:
            start_idx = i
            break

    raw_items = raw_items[start_idx:]

    # Drop leading outliers before the first plausible main sequence.
    # Generic heuristic: if the first few items contain a lower top-level chapter
    # than the very first item, trim everything before that lower chapter begins.
    if raw_items:
        def major_num(item: dict[str, Any]) -> int:
            try:
                return int(str(item.get("id") or "").split(".")[0])
            except Exception:
                return 999999

        majors = [major_num(x) for x in raw_items[:12]]
        if majors:
            min_major = min(majors)
            first_major = majors[0]
            if min_major < first_major:
                for i, item in enumerate(raw_items[:12]):
                    if major_num(item) == min_major:
                        raw_items = raw_items[i:]
                        break

    out: list[dict[str, Any]] = []
    for i, item in enumerate(raw_items):
        start = int(item["start_offset"])
        end = int(raw_items[i + 1]["start_offset"]) if i + 1 < len(raw_items) else len(src)
        item["end_offset"] = end
        out.append(item)

    return out

def _write_sections(doc_id: str, title: str, text: str) -> list[dict[str, Any]]:
    items = _parse_sections_from_text(text)
    _write_json(
        sections_path(doc_id),
        {
            "doc_id": doc_id,
            "title": title,
            "items": items,
        },
    )
    return items


def _section_path_for_offset(sections: list[dict[str, Any]], offset: int) -> list[str]:
    active = []
    for sec in sections:
        try:
            s = int(sec.get("start_offset") or 0)
            e = int(sec.get("end_offset") or 0)
            lvl = int(sec.get("level") or 1)
        except Exception:
            continue
        if s <= offset < e:
            label = f'{sec.get("id", "")} {sec.get("title", "")}'.strip()
            if not label:
                continue
            active = active[: max(0, lvl - 1)]
            active.append(label)
    return active


def write_chunks(doc_id: str, title: str, text: str, sections: list[dict[str, Any]] | None = None) -> int:
    out_path = chunks_path(doc_id)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rows: list[str] = []

    s = _normalize_text(text)
    if not s:
        _write_text(out_path, "")
        return 0

    sections = list(sections or [])
    chunk_chars = 1800
    overlap_chars = 250
    start = 0
    idx = 1
    n = len(s)

    while start < n:
        end = min(n, start + chunk_chars)
        chunk = s[start:end].strip()
        if chunk:
            row = {
                "chunk_id": f"c{idx:04d}",
                "doc_id": doc_id,
                "title": title,
                "section_path": _section_path_for_offset(sections, start),
                "page_start": None,
                "page_end": None,
                "text": chunk,
                "token_estimate": max(1, len(chunk) // 4),
            }
            rows.append(json.dumps(row, ensure_ascii=False))
            idx += 1
        if end >= n:
            break
        start = max(end - overlap_chars, start + 1)

    _write_text(out_path, ("\n".join(rows) + ("\n" if rows else "")))
    return len(rows)


def _safe_title(filename: str, explicit_title: str = "") -> str:
    t = str(explicit_title or "").strip()
    if t:
        return t
    stem = Path(filename).stem.strip()
    return stem or "Untitled document"


def _save_original_file(doc_id: str, src_path: Path) -> Path:
    ensure_docs_dirs()
    raw_doc_dir(doc_id).mkdir(parents=True, exist_ok=True)
    dst = raw_original_path(doc_id, "original.pdf")
    shutil.copy2(src_path, dst)
    return dst



def _load_manifest(doc_id: str) -> dict[str, Any]:
    mp = manifest_path(doc_id)
    if not mp.exists():
        return {}
    try:
        return json.loads(mp.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _registry_item_from_manifest(
    manifest: dict[str, Any],
    *,
    status: str,
    chunk_count: int = 0,
    error: str = "",
) -> dict[str, Any]:
    item = {
        "doc_id": str(manifest.get("doc_id") or ""),
        "title": str(manifest.get("title") or ""),
        "filename": str(manifest.get("filename") or "original.pdf"),
        "content_type": str(manifest.get("content_type") or "application/pdf"),
        "uploaded_at": str(manifest.get("uploaded_at") or iso_z()),
        "uploaded_by": str(manifest.get("uploaded_by") or "admin"),
        "size_bytes": int(manifest.get("size_bytes") or 0),
        "sha256": str(manifest.get("sha256") or ""),
        "status": status,
        "active": bool(manifest.get("active", True)),
        "source": str(manifest.get("source") or "local_upload"),
        "parser_version": str(manifest.get("parser_version") or "v2-ocr"),
        "chunk_count": int(chunk_count or 0),
    }
    if error:
        item["error"] = str(error)
    return item


def queue_uploaded_pdf(
    *,
    temp_upload_path: Path,
    original_filename: str,
    content_type: str,
    uploaded_by: str = "admin",
    title: str = "",
) -> dict[str, Any]:
    ensure_docs_dirs()

    doc_id = make_doc_id()
    raw_path = _save_original_file(doc_id, temp_upload_path)
    derived_doc_dir(doc_id).mkdir(parents=True, exist_ok=True)

    sha = sha256_file(raw_path)
    size_bytes = raw_path.stat().st_size
    doc_title = _safe_title(original_filename, title)

    manifest = {
        "doc_id": doc_id,
        "filename": str(original_filename or "original.pdf"),
        "title": doc_title,
        "content_type": str(content_type or "application/pdf"),
        "sha256": sha,
        "size_bytes": size_bytes,
        "uploaded_at": iso_z(),
        "uploaded_by": str(uploaded_by or "admin"),
        "source": "local_upload",
        "active": True,
        "status": "queued",
        "parser_version": "v2-ocr",
        "tags": [],
    }
    write_manifest(doc_id, manifest)
    write_status(doc_id, status="queued", steps={})
    initialize_sections_placeholder(doc_id, doc_title)

    upsert_doc(_registry_item_from_manifest(manifest, status="queued", chunk_count=0))

    return {
        "ok": True,
        "queued": True,
        "doc_id": doc_id,
        "status": "queued",
        "chunk_count": 0,
        "title": doc_title,
        "filename": str(original_filename or "original.pdf"),
    }


def process_queued_pdf(doc_id: str) -> dict[str, Any]:
    ensure_docs_dirs()

    manifest = _load_manifest(doc_id)
    raw_path = raw_original_path(doc_id, "original.pdf")

    if not manifest:
        raise RuntimeError(f"document manifest missing for {doc_id}")
    if not raw_path.exists():
        raise RuntimeError(f"document source missing for {doc_id}")

    manifest["status"] = "processing"
    manifest["parser_version"] = "v2-ocr"
    write_manifest(doc_id, manifest)
    write_status(doc_id, status="processing", steps={})
    upsert_doc(_registry_item_from_manifest(manifest, status="processing", chunk_count=0))

    try:
        errors_path(doc_id).unlink(missing_ok=True)
    except Exception:
        pass

    doc_title = str(manifest.get("title") or "")
    steps: dict[str, Any] = {}

    try:
        write_status(doc_id, status="extracting", steps=steps)
        text, extract_mode = extract_pdf_text(raw_path)
        _write_text(extract_path(doc_id), text)
        steps["extract"] = {"ok": True, "mode": extract_mode}

        write_status(doc_id, status="structuring", steps=steps)
        sections = _write_sections(doc_id, doc_title, text)
        steps["structure"] = {"ok": True, "mode": "heading_parser", "count": len(sections)}

        write_status(doc_id, status="chunking", steps=steps)
        chunk_count = write_chunks(doc_id, doc_title, text, sections=sections)
        steps["chunk"] = {"ok": True, "count": chunk_count}

        manifest["status"] = "ready"
        manifest["parser_version"] = "v2-ocr"
        write_manifest(doc_id, manifest)
        write_status(doc_id, status="ready", steps=steps)

        upsert_doc(_registry_item_from_manifest(manifest, status="ready", chunk_count=chunk_count))

        return {
            "ok": True,
            "doc_id": doc_id,
            "status": "ready",
            "chunk_count": chunk_count,
        }

    except Exception as e:
        err = str(e)
        _write_text(errors_path(doc_id), err + "\n")

        manifest["status"] = "failed"
        manifest["parser_version"] = "v2-ocr"
        write_manifest(doc_id, manifest)
        write_status(doc_id, status="failed", steps=steps, error=err)

        upsert_doc(_registry_item_from_manifest(manifest, status="failed", chunk_count=0, error=err))

        return {
            "ok": False,
            "doc_id": doc_id,
            "status": "failed",
            "error": err,
        }


def ingest_uploaded_pdf(
    *,
    temp_upload_path: Path,
    original_filename: str,
    content_type: str,
    uploaded_by: str = "admin",
    title: str = "",
) -> dict[str, Any]:
    queued = queue_uploaded_pdf(
        temp_upload_path=temp_upload_path,
        original_filename=original_filename,
        content_type=content_type,
        uploaded_by=uploaded_by,
        title=title,
    )
    return process_queued_pdf(str(queued["doc_id"]))
