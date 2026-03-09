from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter

router = APIRouter(prefix="/api/llm2", tags=["llm2"])

STATE_ROOT = Path("/opt/tak/tools/takctl/state/llm2")
LATEST_ROOT = STATE_ROOT / "latest"
RUNS_ROOT = STATE_ROOT / "runs"

MAX_TEXT_CHARS = 20000  # keep UI payload sane


def _read_json(p: Path) -> Dict[str, Any]:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "path": str(p)}


def _read_text_limited(p: Path) -> str:
    try:
        s = p.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"[error reading {p}: {type(e).__name__}: {e}]"
    if len(s) <= MAX_TEXT_CHARS:
        return s
    return s[:MAX_TEXT_CHARS] + "\n\n[...truncated...]\n"


def _latest_phase(domain: str, phase: str) -> Dict[str, Any]:
    d = LATEST_ROOT / domain / phase
    out: Dict[str, Any] = {"ok": True, "dir": str(d), "files": {}}
    if not d.exists():
        out["ok"] = False
        out["error"] = "missing"
        return out

    # Keep this conservative; UI renders these directly.
    json_names = ["latest.json", "trace.json", "findings.json", "card.json"]
    for name in json_names:
        p = d / name
        if p.exists():
            out["files"][name] = _read_json(p)

    return out


def _run_phase_files(run_id: str, domain: str, phase: str) -> Dict[str, Any]:
    """
    Read per-run artifacts for deep debugging:
      runs/<rid>/<domain>/<phase>/{prompt.txt,response_text.txt,cleaned_text.txt,request.json,response.http.json}
    Returned shape is UI-friendly and size-capped for text.
    """
    d = RUNS_ROOT / run_id / domain / phase
    out: Dict[str, Any] = {"ok": True, "dir": str(d)}
    if not d.exists():
        out["ok"] = False
        out["error"] = "missing"
        return out

    # Text
    for name in ("prompt.txt", "response_text.txt", "cleaned_text.txt"):
        p = d / name
        if p.exists():
            out[name.replace(".", "_")] = _read_text_limited(p)

    # JSON
    for name in ("request.json", "response.http.json"):
        p = d / name
        if p.exists():
            out[name.replace(".", "_")] = _read_json(p)

    return out


def _get_run_id(run_obj: Any) -> Optional[str]:
    if isinstance(run_obj, dict):
        rid = run_obj.get("run_id") or run_obj.get("rid")
        if isinstance(rid, str) and rid.strip():
            return rid.strip()
    return None


@router.get("/latest")
def latest() -> Dict[str, Any]:
    """
    UI-friendly snapshot of llm2 state under:
      /opt/tak/tools/takctl/state/llm2/latest
    plus optional deep debug excerpts from:
      /opt/tak/tools/takctl/state/llm2/runs/<run_id>/...
    """
    resp: Dict[str, Any] = {
        "ok": True,
        "state_root": str(STATE_ROOT),
        "latest_root": str(LATEST_ROOT),
        "runs_root": str(RUNS_ROOT),
        "run": None,
        "domains": {},
    }

    run_ptr = LATEST_ROOT / "run.latest.json"
    resp["run"] = _read_json(run_ptr) if run_ptr.exists() else {"ok": False, "error": "missing", "path": str(run_ptr)}
    run_id = _get_run_id(resp["run"])

    if not LATEST_ROOT.exists():
        resp["ok"] = False
        resp["error"] = "latest_root_missing"
        return resp

    for dom_dir in sorted([p for p in LATEST_ROOT.iterdir() if p.is_dir()]):
        dom = dom_dir.name
        dom_obj: Dict[str, Any] = {
            "phase1": _latest_phase(dom, "phase1"),
            "phase2": _latest_phase(dom, "phase2"),
            "phase3": _latest_phase(dom, "phase3"),
        }

        # Deep debug: pull run artifacts for this domain if we know the run_id.
        if run_id:
            dom_obj["run_files"] = {
                "phase1": _run_phase_files(run_id, dom, "phase1"),
                "phase2": _run_phase_files(run_id, dom, "phase2"),
                "phase3": _run_phase_files(run_id, dom, "phase3"),
            }

        resp["domains"][dom] = dom_obj

    return resp
