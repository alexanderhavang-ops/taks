from __future__ import annotations

import json
import os
import tempfile
import zipfile
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


def _ingest_one_pdf_bytes(
    *,
    data: bytes,
    filename: str,
    content_type: str,
    uploaded_by: str,
    title: str,
) -> dict:
    fd, tmp_name = tempfile.mkstemp(prefix="takctl-doc-upload-", suffix=".pdf")
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        tmp_path.write_bytes(data)
        return ingest_uploaded_pdf(
            temp_upload_path=tmp_path,
            original_filename=filename,
            content_type=content_type,
            uploaded_by=uploaded_by,
            title=title,
        )
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass


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

    data = await file.read()
    lower = filename.lower()

    if lower.endswith(".pdf"):
        out = _ingest_one_pdf_bytes(
            data=data,
            filename=filename,
            content_type=content_type or "application/pdf",
            uploaded_by="admin",
            title=title,
        )
        out["mode"] = "pdf"
        return out

    if not lower.endswith(".zip"):
        raise HTTPException(status_code=400, detail="only PDF or ZIP upload is supported")

    try:
        zf = zipfile.ZipFile(Path(filename), mode="r")
    except Exception:
        pass

    items = []
    skipped = []
    pdf_members = []

    try:
        from io import BytesIO
        with zipfile.ZipFile(BytesIO(data), mode="r") as z:
            for info in z.infolist():
                if info.is_dir():
                    continue
                member_name = str(info.filename or "")
                member_base = Path(member_name).name
                if not member_base:
                    continue
                if member_base.startswith("._"):
                    skipped.append({"name": member_name, "reason": "macos_sidecar"})
                    continue
                if not member_base.lower().endswith(".pdf"):
                    skipped.append({"name": member_name, "reason": "not_pdf"})
                    continue
                pdf_members.append((info, member_base))

            if not pdf_members:
                raise HTTPException(status_code=400, detail="zip contained no PDF files")

            single_title = title if len(pdf_members) == 1 else ""

            for info, member_base in pdf_members:
                try:
                    member_data = z.read(info)
                    result = _ingest_one_pdf_bytes(
                        data=member_data,
                        filename=member_base,
                        content_type="application/pdf",
                        uploaded_by="admin",
                        title=single_title,
                    )
                    result["source_name"] = str(info.filename or member_base)
                    items.append(result)
                except Exception as e:
                    items.append({
                        "ok": False,
                        "status": "failed",
                        "source_name": str(info.filename or member_base),
                        "filename": member_base,
                        "error": str(e),
                    })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"invalid zip: {e}")

    ok_count = sum(1 for x in items if x.get("ok"))
    fail_count = sum(1 for x in items if not x.get("ok"))

    return {
        "ok": fail_count == 0,
        "mode": "zip",
        "filename": filename,
        "count_total": len(items),
        "count_ok": ok_count,
        "count_failed": fail_count,
        "count_skipped": len(skipped),
        "items": items,
        "skipped": skipped[:200],
    }


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
