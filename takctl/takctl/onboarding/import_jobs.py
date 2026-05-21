from __future__ import annotations

import json
import shutil
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from takctl.config import load_config
from takctl.onboarding.service_builder import build_service
from takctl.onboarding.import_users import load_file, run_import

ROOT = Path("/opt/tak/takctl-state/onboarding/import-jobs")
JOBS_DIR = ROOT / "jobs"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _job_id() -> str:
    return _now_utc().strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]


def _ensure_dirs() -> None:
    JOBS_DIR.mkdir(parents=True, exist_ok=True)


def _job_dir(job_id: str) -> Path:
    return JOBS_DIR / job_id


def _job_json_path(job_id: str) -> Path:
    return _job_dir(job_id) / "job.json"


def _result_json_path(job_id: str) -> Path:
    return _job_dir(job_id) / "result.json"


def _events_path(job_id: str) -> Path:
    return _job_dir(job_id) / "events.jsonl"


def _external_base_from_config() -> str | None:
    cfg = load_config()
    v = (getattr(cfg, "onboarding_external_base", "") or "").strip()
    return v.rstrip("/") if v else None


def _write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def _append_event(job_id: str, event: Dict[str, Any]) -> None:
    p = _events_path(job_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, sort_keys=True) + "\n")


def create_job_from_upload(
    *,
    upload_path: str,
    source_filename: str,
    dry_run: bool,
    update_existing: bool,
    requested_by: str = "web",
) -> Dict[str, Any]:
    _ensure_dirs()

    job_id = _job_id()
    jdir = _job_dir(job_id)
    jdir.mkdir(parents=True, exist_ok=True)

    ext = Path(source_filename or upload_path).suffix.lower() or ".xlsx"
    source_copy = jdir / f"source{ext}"
    shutil.copy2(upload_path, source_copy)

    total_rows = 0
    try:
        total_rows = len(load_file(str(source_copy)))
    except Exception:
        total_rows = 0

    external_base = _external_base_from_config()

    job = {
        "job_id": job_id,
        "state": "queued",
        "created_at": _iso(_now_utc()),
        "started_at": None,
        "finished_at": None,
        "requested_by": requested_by,
        "source_filename": source_filename,
        "source_path": str(source_copy),
        "dry_run": bool(dry_run),
        "update_existing": bool(update_existing),
        "external_base": external_base,
        "total_rows": int(total_rows),
        "done_rows": 0,
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "error_count": 0,
        "current_row": None,
        "current_username": None,
        "last_error": None,
    }

    _write_json(_job_json_path(job_id), job)
    _append_event(job_id, {"ts": _iso(_now_utc()), "type": "job_created", "job_id": job_id})
    return job


def load_job(job_id: str) -> Dict[str, Any]:
    p = _job_json_path(job_id)
    if not p.exists():
        raise FileNotFoundError(job_id)
    return json.loads(p.read_text(encoding="utf-8"))


def save_job(job: Dict[str, Any]) -> None:
    _write_json(_job_json_path(str(job["job_id"])), job)


def list_jobs(limit: int = 50) -> List[Dict[str, Any]]:
    _ensure_dirs()
    out: List[Dict[str, Any]] = []
    for p in sorted(JOBS_DIR.glob("*/job.json"), reverse=True):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            continue
        if len(out) >= int(limit):
            break
    return out


def load_result(job_id: str) -> Optional[Dict[str, Any]]:
    p = _result_json_path(job_id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _summarize_result(job: Dict[str, Any], result: Dict[str, Any]) -> None:
    job["created"] = int(result.get("created", 0) or 0)
    job["updated"] = int(result.get("updated", 0) or 0)
    job["skipped"] = int(result.get("skipped", 0) or 0)
    errs = result.get("errors") or []
    job["error_count"] = len(errs)
    if errs:
        last = errs[-1]
        job["last_error"] = str((last or {}).get("error") or "unknown error")


def _make_progress_cb(job_id: str):
    def _progress(payload: Dict[str, Any]) -> None:
        try:
            job = load_job(job_id)
        except Exception:
            return

        job["done_rows"] = int(payload.get("row", 0) or 0)
        job["current_row"] = int(payload.get("row", 0) or 0)
        job["current_username"] = payload.get("username")
        job["created"] = int(payload.get("created", 0) or 0)
        job["updated"] = int(payload.get("updated", 0) or 0)
        job["skipped"] = int(payload.get("skipped", 0) or 0)
        job["error_count"] = int(payload.get("error_count", 0) or 0)

        if payload.get("status") == "error":
            job["last_error"] = str(payload.get("error") or "unknown error")

        save_job(job)

        _append_event(job_id, {
            "ts": _iso(_now_utc()),
            "type": "row_progress",
            "row": job["current_row"],
            "username": job["current_username"],
            "status": payload.get("status"),
            "created": job["created"],
            "updated": job["updated"],
            "skipped": job["skipped"],
            "error_count": job["error_count"],
        })

    return _progress


def run_job(job_id: str) -> None:
    job = load_job(job_id)
    if job.get("state") not in ("queued", "running"):
        return

    job["state"] = "running"
    job["started_at"] = _iso(_now_utc())
    save_job(job)
    _append_event(job_id, {"ts": _iso(_now_utc()), "type": "job_started", "job_id": job_id})

    try:
        svc = build_service(external_base=job.get("external_base"))
        result = run_import(
            svc,
            str(job["source_path"]),
            dry_run=bool(job.get("dry_run", False)),
            update_existing=bool(job.get("update_existing", False)),
            progress_cb=_make_progress_cb(job_id),
        )

        _write_json(_result_json_path(job_id), result)
        _summarize_result(job, result)
        job["done_rows"] = int(result.get("rows", 0) or 0)
        job["current_row"] = None
        job["current_username"] = None
        job["state"] = "done"
        job["finished_at"] = _iso(_now_utc())
        save_job(job)

        _append_event(job_id, {
            "ts": _iso(_now_utc()),
            "type": "job_finished",
            "job_id": job_id,
            "created": job["created"],
            "updated": job["updated"],
            "skipped": job["skipped"],
            "error_count": job["error_count"],
        })
    except Exception as e:
        job["state"] = "failed"
        job["finished_at"] = _iso(_now_utc())
        job["last_error"] = f"{type(e).__name__}: {e}"
        save_job(job)
        _append_event(job_id, {
            "ts": _iso(_now_utc()),
            "type": "job_failed",
            "job_id": job_id,
            "error": job["last_error"],
        })


def _run_job_thread(job_id: str) -> None:
    run_job(job_id)


def start_job_thread(job_id: str) -> None:
    t = threading.Thread(target=_run_job_thread, args=(job_id,), daemon=True)
    t.start()
