from __future__ import annotations

import hashlib
import json
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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


def extract_pdf_text(pdf_path: Path) -> str:
    # KISS: try pypdf first, then pdftotext if available.
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


def write_chunks(doc_id: str, title: str, text: str) -> int:
    out_path = chunks_path(doc_id)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rows: list[str] = []
    for idx, chunk in enumerate(_chunk_text(text), start=1):
        row = {
            "chunk_id": f"c{idx:04d}",
            "doc_id": doc_id,
            "title": title,
            "section_path": [],
            "page_start": None,
            "page_end": None,
            "text": chunk,
            "token_estimate": max(1, len(chunk) // 4),
        }
        rows.append(json.dumps(row, ensure_ascii=False))
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


def ingest_uploaded_pdf(
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
        "status": "uploaded",
        "parser_version": "v1",
        "tags": [],
    }
    write_manifest(doc_id, manifest)
    write_status(doc_id, status="uploaded", steps={})
    initialize_sections_placeholder(doc_id, doc_title)

    steps: dict[str, Any] = {}

    try:
        write_status(doc_id, status="extracting", steps=steps)
        text = extract_pdf_text(raw_path)
        _write_text(extract_path(doc_id), text)
        steps["extract"] = {"ok": True}

        write_status(doc_id, status="chunking", steps=steps)
        chunk_count = write_chunks(doc_id, doc_title, text)
        steps["chunk"] = {"ok": True, "count": chunk_count}

        steps["structure"] = {"ok": True, "mode": "placeholder"}
        manifest["status"] = "ready"
        write_manifest(doc_id, manifest)
        write_status(doc_id, status="ready", steps=steps)

        upsert_doc(
            {
                "doc_id": doc_id,
                "title": doc_title,
                "filename": str(original_filename or "original.pdf"),
                "content_type": str(content_type or "application/pdf"),
                "uploaded_at": manifest["uploaded_at"],
                "uploaded_by": str(uploaded_by or "admin"),
                "size_bytes": size_bytes,
                "sha256": sha,
                "status": "ready",
                "active": True,
                "source": "local_upload",
                "parser_version": "v1",
                "chunk_count": chunk_count,
            }
        )

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
        write_manifest(doc_id, manifest)
        write_status(doc_id, status="failed", steps=steps, error=err)

        upsert_doc(
            {
                "doc_id": doc_id,
                "title": doc_title,
                "filename": str(original_filename or "original.pdf"),
                "content_type": str(content_type or "application/pdf"),
                "uploaded_at": manifest["uploaded_at"],
                "uploaded_by": str(uploaded_by or "admin"),
                "size_bytes": size_bytes,
                "sha256": sha,
                "status": "failed",
                "active": True,
                "source": "local_upload",
                "parser_version": "v1",
                "chunk_count": 0,
                "error": err,
            }
        )
        return {
            "ok": False,
            "doc_id": doc_id,
            "status": "failed",
            "error": err,
        }
