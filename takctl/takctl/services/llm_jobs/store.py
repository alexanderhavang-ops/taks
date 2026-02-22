from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Optional


def _now() -> int:
    return int(time.time())


def _default_state_dir() -> Path:
    """
    Prefer runtime-owned state; fall back safely for dev.

    NOTE: In source tree tests this may end up in /tmp.
    In runtime, /opt/tak/tools/takctl/state should exist.
    """
    candidates = [
        os.environ.get("TAKCTL_STATE_DIR", "").strip(),
        "/opt/tak/tools/takctl/state",
        "/opt/tak/state",
        "/var/lib/takctl",
        "/tmp/takctl-state",
    ]
    for c in candidates:
        if not c:
            continue
        p = Path(c)
        try:
            p.mkdir(parents=True, exist_ok=True)
            return p
        except Exception:
            continue
    return Path("/tmp/takctl-state")


def llm_state_dir() -> Path:
    p = _default_state_dir() / "llm"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _job_path(job_id: str) -> Path:
    return llm_state_dir() / f"job-{job_id}.json"


def _latest_path(view: str) -> Path:
    safe = "".join(ch if (ch.isalnum() or ch in "-_.") else "_" for ch in (view or "view"))
    return llm_state_dir() / f"latest-{safe}.json"


def new_job(view: str) -> dict[str, Any]:
    job_id = uuid.uuid4().hex
    rec = {
        "ok": True,
        "job_id": job_id,
        "view": view,
        "status": "queued",
        "created_ts": _now(),
        "updated_ts": _now(),
    }
    write_job(rec)
    return rec


def write_job(rec: dict[str, Any]) -> None:
    rec = dict(rec)
    rec["updated_ts"] = _now()
    job_id = str(rec.get("job_id") or "")
    if not job_id:
        return
    p = _job_path(job_id)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(rec, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(p)


def read_job(job_id: str) -> Optional[dict[str, Any]]:
    p = _job_path(job_id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def write_latest(view: str, plan: dict[str, Any]) -> None:
    p = _latest_path(view)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(p)


def read_latest(view: str) -> Optional[dict[str, Any]]:
    p = _latest_path(view)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
