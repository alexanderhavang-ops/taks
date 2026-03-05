from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter

router = APIRouter(prefix="/api/llm2", tags=["llm2"])

STATE_ROOT = Path("/opt/tak/tools/takctl/state/llm2")
LATEST_ROOT = STATE_ROOT / "latest"
RUNS_ROOT = STATE_ROOT / "runs"


def _read_json(p: Path) -> Dict[str, Any]:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "path": str(p)}


def _latest_phase(domain: str, phase: str) -> Dict[str, Any]:
    d = LATEST_ROOT / domain / phase
    out: Dict[str, Any] = {"ok": True, "dir": str(d), "files": {}}
    if not d.exists():
        out["ok"] = False
        out["error"] = "missing"
        return out
    for name in ("latest.json", "trace.json"):
        p = d / name
        if p.exists():
            out["files"][name] = _read_json(p)
    return out


@router.get("/latest")
def latest() -> Dict[str, Any]:
    """
    UI-friendly snapshot of llm2 state under:
      /opt/tak/tools/takctl/state/llm2/latest
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
    resp["run"] = _read_json(run_ptr) if run_ptr.exists() else {
        "ok": False, "error": "missing", "path": str(run_ptr)
    }

    if not LATEST_ROOT.exists():
        resp["ok"] = False
        resp["error"] = "latest_root_missing"
        return resp

    for dom_dir in sorted([p for p in LATEST_ROOT.iterdir() if p.is_dir()]):
        dom = dom_dir.name
        resp["domains"][dom] = {
            "phase1": _latest_phase(dom, "phase1"),
            "phase2": _latest_phase(dom, "phase2"),
            "phase3": _latest_phase(dom, "phase3"),
        }

    return resp
