from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from takctl.services.docs_ingest import ingest_uploaded_pdf
from takctl.services.docs_paths import (
    ensure_docs_dirs,
    manifest_path,
    status_path,
    extract_path,
)
from takctl.services.docs_registry import list_docs, get_doc, delete_doc_entry

router = APIRouter(prefix="/api/docs", tags=["documents"])


@router.get("")
def api_list_docs():
    ensure_docs_dirs()
    return {"ok": True, "items": list_docs()}


@router.get("/{doc_id}")
def api_get_doc(doc_id: str):
    ensure_docs_dirs()
    item = get_doc(doc_id)
    if item is None:
        raise HTTPException(status_code=404, detail="document not found")

    mp = manifest_path(doc_id)
    sp = status_path(doc_id)
    ep = extract_path(doc_id)

    manifest = {}
    status = {}
    extract_preview = ""

    try:
        if mp.exists():
            manifest = json.loads(mp.read_text(encoding="utf-8"))
    except Exception:
        manifest = {}

    try:
        if sp.exists():
            status = json.loads(sp.read_text(encoding="utf-8"))
    except Exception:
        status = {}

    try:
        if ep.exists():
            extract_preview = ep.read_text(encoding="utf-8")[:2000]
    except Exception:
        extract_preview = ""

    return {
        "ok": True,
        "item": item,
        "manifest": manifest,
        "status": status,
        "extract_preview": extract_preview,
    }


@router.post("/upload")
async def api_upload_doc(
    file: UploadFile = File(...),
    title: str = Form(default=""),
):
    ensure_docs_dirs()

    filename = str(file.filename or "").strip()
    content_type = str(file.content_type or "application/octet-stream")

    if not filename:
        raise HTTPException(status_code=400, detail="missing filename")
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="only PDF upload is supported in v1")

    fd, tmp_name = tempfile.mkstemp(prefix="takctl-doc-upload-", suffix=".pdf")
    os.close(fd)
    tmp_path = Path(tmp_name)

    try:
        data = await file.read()
        tmp_path.write_bytes(data)

        result = ingest_uploaded_pdf(
            temp_upload_path=tmp_path,
            original_filename=filename,
            content_type=content_type,
            uploaded_by="admin",
            title=title,
        )
        return result
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass


@router.delete("/{doc_id}")
def api_delete_doc(doc_id: str):
    ensure_docs_dirs()
    item = get_doc(doc_id)
    if item is None:
        raise HTTPException(status_code=404, detail="document not found")

    import shutil

    for p in [manifest_path(doc_id), status_path(doc_id), extract_path(doc_id)]:
        try:
            p.unlink(missing_ok=True)
        except Exception:
            pass

    try:
        shutil.rmtree(str(Path("/opt/tak/tools/takctl/state/docs/raw") / doc_id), ignore_errors=True)
    except Exception:
        pass

    try:
        shutil.rmtree(str(Path("/opt/tak/tools/takctl/state/docs/derived") / doc_id), ignore_errors=True)
    except Exception:
        pass

    delete_doc_entry(doc_id)
    return {"ok": True, "doc_id": doc_id, "deleted": True}
