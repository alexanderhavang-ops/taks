from __future__ import annotations

import os
import time
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse

from takctl.api.onboarding_identity import build_service
from takctl.onboarding.import_jobs import (
    create_job_from_upload,
    list_jobs,
    load_job,
    load_result,
    start_job_thread,
)
from takctl.onboarding.import_users_preview import preview_import
from takctl.onboarding.import_users import run_import

router = APIRouter(prefix="/api/onboarding/import")

_TMP_DIR = Path(os.environ.get("TAKS_IMPORT_TMP", "/tmp"))


def _save_upload(upload: UploadFile) -> Path:
    name = (upload.filename or "upload.xlsx").strip()
    ext = (Path(name).suffix or ".xlsx").lower()
    if ext not in (".xlsx", ".csv"):
        raise HTTPException(status_code=400, detail=f"unsupported file type: {ext} (expected .xlsx or .csv)")

    _TMP_DIR.mkdir(parents=True, exist_ok=True)
    p = _TMP_DIR / f"taks-import-{int(time.time())}-{os.getpid()}{ext}"

    with p.open("wb") as f:
        while True:
            chunk = upload.file.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)
    return p


@router.post("/preview")
def import_preview(req: Request, file: UploadFile = File(...), sample_n: int = 5):
    p = _save_upload(file)
    out = preview_import(str(p), sample_n=int(sample_n))
    out["upload_tmp_path"] = str(p)
    return JSONResponse(out, headers={"cache-control": "no-store, max-age=0", "pragma": "no-cache"})


# ---------------------------------------------------------------------
# Phase 1 legacy synchronous apply (keep for now, small imports only)
# ---------------------------------------------------------------------
@router.post("/apply")
def import_apply(
    req: Request,
    file: UploadFile = File(...),
    dry_run: bool = False,
    update_existing: bool = False,
):
    p = _save_upload(file)
    svc = build_service()
    res = run_import(
        svc,
        str(p),
        dry_run=bool(dry_run),
        update_existing=bool(update_existing),
    )
    res["upload_tmp_path"] = str(p)
    return JSONResponse(res, headers={"cache-control": "no-store, max-age=0", "pragma": "no-cache"})


# ---------------------------------------------------------------------
# Phase 2 async import jobs
# ---------------------------------------------------------------------
@router.post("/jobs")
def create_import_job(
    req: Request,
    file: UploadFile = File(...),
    dry_run: bool = False,
    update_existing: bool = False,
):
    p = _save_upload(file)

    job = create_job_from_upload(
        upload_path=str(p),
        source_filename=(file.filename or "upload.xlsx"),
        dry_run=bool(dry_run),
        update_existing=bool(update_existing),
        requested_by="web",
    )

    start_job_thread(str(job["job_id"]))

    return JSONResponse(
        {
            "job_id": job["job_id"],
            "state": job["state"],
            "created_at": job["created_at"],
            "total_rows": job["total_rows"],
        },
        headers={"cache-control": "no-store, max-age=0", "pragma": "no-cache"},
    )


@router.get("/jobs")
def get_import_jobs(limit: int = Query(50, ge=1, le=500)):
    jobs = list_jobs(limit=int(limit))
    return JSONResponse(
        {"jobs": jobs},
        headers={"cache-control": "no-store, max-age=0", "pragma": "no-cache"},
    )


@router.get("/jobs/{job_id}")
def get_import_job(job_id: str):
    try:
        job = load_job(job_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="job not found")

    result = load_result(job_id)
    out = {"job": job}
    if result is not None:
        out["result"] = result

    return JSONResponse(
        out,
        headers={"cache-control": "no-store, max-age=0", "pragma": "no-cache"},
    )
