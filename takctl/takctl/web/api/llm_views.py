from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter

from takctl.services.llm import llm_status

router = APIRouter(prefix="/api/llm", tags=["llm"])


# -----------------------------------------------------------------------------
# Core helpers
# -----------------------------------------------------------------------------

def _state_root() -> Path:
    base = (os.environ.get("TAKCTL_STATE_DIR") or "").strip() or "/opt/tak/tools/takctl/state"
    p = Path(base) / "llm" / "tactical-operations"
    p.mkdir(parents=True, exist_ok=True)
    (p / "runs").mkdir(parents=True, exist_ok=True)
    return p


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"ok": False, "error": "not_found", "path": str(path)}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"ok": False, "error": f"read_failed: {type(e).__name__}: {e}", "path": str(path)}


def _safe_run_id(run_id: str) -> str | None:
    rid = (run_id or "").strip()
    # run ids like 20260221T161459Z
    if not re.fullmatch(r"[0-9]{8}T[0-9]{6}Z", rid):
        return None
    return rid


# -----------------------------------------------------------------------------
# LLM status (shared with CLI)
# -----------------------------------------------------------------------------

@router.get("/status")
def api_llm_status() -> dict[str, Any]:
    # single source of truth (same as CLI uses)
    return llm_status(None)


# -----------------------------------------------------------------------------
# Tactical Operations (read-only, systemd-owned generation)
# -----------------------------------------------------------------------------

@router.get("/views/tactical/latest")
def api_llm_tactical_latest() -> dict[str, Any]:
    root = _state_root()
    return _read_json(root / "latest.json")


@router.get("/views/tactical/last_run")
def api_llm_tactical_last_run() -> dict[str, Any]:
    root = _state_root()
    return _read_json(root / "last_run.json")


@router.get("/views/tactical/snapshot")
def api_llm_tactical_snapshot() -> dict[str, Any]:
    root = _state_root()
    return _read_json(root / "snapshot.json")


@router.get("/views/tactical/history")
def api_llm_tactical_history(limit: int = 20) -> dict[str, Any]:
    root = _state_root()
    runs_dir = root / "runs"
    items: list[dict[str, Any]] = []
    try:
        files = sorted(runs_dir.glob("*.json"), key=lambda p: p.name, reverse=True)
        for p in files[: max(1, min(int(limit), 200))]:
            items.append({"name": p.name, "path": str(p), "mtime": int(p.stat().st_mtime)})
        return {"ok": True, "count": len(items), "runs": items}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


# -----------------------------------------------------------------------------
# Findings (deterministic aggregation runner output)
# -----------------------------------------------------------------------------

def _findings_root() -> Path:
    return _state_root() / "findings"


@router.get("/views/tactical/findings/latest")
def api_llm_tactical_findings_latest() -> dict[str, Any]:
    root = _findings_root()
    return _read_json(root / "latest.json")


@router.get("/views/tactical/findings/trace")
def api_llm_tactical_findings_trace(run_id: str = "") -> dict[str, Any]:
    """
    Compatibility alias.

    If run_id is omitted, resolves findings/latest.json then returns that run's trace.json.
    """
    root = _findings_root()
    rid = (run_id or "").strip()
    if not rid:
        latest = _read_json(root / "latest.json")
        rid = str(latest.get("run_id") or "").strip()
        if not rid:
            return {"ok": False, "error": "no_latest_findings", "latest": latest}

    rid2 = _safe_run_id(rid)
    if not rid2:
        return {"ok": False, "error": "bad_run_id", "run_id": rid}

    return _read_json(root / rid2 / "trace.json")


@router.get("/views/tactical/findings/history")
def api_llm_tactical_findings_history(limit: int = 20) -> dict[str, Any]:
    root = _findings_root()
    items: list[dict[str, Any]] = []
    try:
        if not root.exists():
            return {"ok": True, "count": 0, "runs": []}
        dirs = [d for d in root.iterdir() if d.is_dir()]
        dirs = sorted(dirs, key=lambda d: d.name, reverse=True)
        for d in dirs[: max(1, min(int(limit), 200))]:
            trace = d / "trace.json"
            bundle = d / "baseline_latest_bundle.json"
            items.append(
                {
                    "run_id": d.name,
                    "dir": str(d),
                    "mtime": int(d.stat().st_mtime),
                    "has_trace": trace.exists(),
                    "has_bundle": bundle.exists(),
                    "trace_bytes": trace.stat().st_size if trace.exists() else None,
                }
            )
        return {"ok": True, "count": len(items), "runs": items}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


@router.get("/views/tactical/findings/run/{run_id}")
def api_llm_tactical_findings_run(run_id: str) -> dict[str, Any]:
    rid = _safe_run_id(run_id)
    if not rid:
        return {"ok": False, "error": "bad_run_id", "run_id": run_id}

    root = _findings_root()
    d = root / rid

    # Hard safety: must be a direct child dir of findings/
    try:
        if d.resolve().parent != root.resolve():
            return {"ok": False, "error": "bad_path", "run_id": rid}
    except Exception:
        return {"ok": False, "error": "resolve_failed", "run_id": rid}

    if not d.exists() or not d.is_dir():
        return {"ok": False, "error": "not_found", "run_id": rid, "dir": str(d)}

    trace = _read_json(d / "trace.json")
    bundle = _read_json(d / "baseline_latest_bundle.json")

    return {"ok": True, "run_id": rid, "dir": str(d), "trace": trace, "baseline_latest_bundle": bundle}


# -----------------------------------------------------------------------------
# Findings/context (LLM prompt input)
# NOTE: context builder is already in your runtime file; keep it as-is here by
# delegating to the existing implementation if present in trace.
# We keep this endpoint minimal: it returns the already-built context artifact.
# -----------------------------------------------------------------------------

def _build_findings_context_from_trace(trace: dict[str, Any]) -> dict[str, Any]:
    """
    Minimal builder: expects trace produced by deterministic runner includes enough
    info to expose Phase0 queries (sql_head/columns/sample).
    This keeps the endpoint stable even if trace format evolves.
    """
    out: dict[str, Any] = {
        "ok": True,
        "run_id": trace.get("run_id"),
        "generated_utc": trace.get("generated_utc"),
        "baseline_run_id": None,
        "queries": [],
    }

    stages = trace.get("stages") or []
    for st in stages:
        if isinstance(st, dict) and st.get("stage") == "baseline":
            out["baseline_run_id"] = st.get("baseline_run_id")
            qs = st.get("queries") or []
            for q in qs:
                if not isinstance(q, dict):
                    continue
                out["queries"].append(
                    {
                        "name": q.get("name"),
                        "row_count": q.get("row_count"),
                        "sql_head": q.get("sql_head") or q.get("sql") or "",
                        "columns": q.get("columns") or [],
                        "sample": q.get("sample") or q.get("result_preview") or [],
                    }
                )
            break

    return out


@router.get("/views/tactical/findings/context")
def api_llm_tactical_findings_context(run_id: str = "") -> dict[str, Any]:
    """
    Phase 0 context as JSON (compact + safe).
    """
    trace = api_llm_tactical_findings_trace(run_id=run_id)
    if not trace or not trace.get("run_id"):
        return {"ok": False, "error": "no_trace", "trace": trace}
    return _build_findings_context_from_trace(trace)


# -----------------------------------------------------------------------------
# Decorated schema exposure (what we give the LLM)
# -----------------------------------------------------------------------------

def _repo_schema_candidates() -> list[Path]:
    # Source tree (repo) candidates — safe fallback so UI always shows *something*.
    return [
        Path("/opt/taks/llm-infra/schema/mission_microdomain_contract.json"),
        Path("/opt/taks/llm-infra/schema/mission_microdomain_safe.json"),
    ]


def _runtime_schema_candidates(run_id: Optional[str]) -> list[Path]:
    # Runtime/state candidates — if/when the runner writes a decorated schema artifact.
    root = _state_root()
    fr = _findings_root()

    cands: list[Path] = []

    rid = _safe_run_id(run_id or "") if run_id else None
    if rid:
        cands += [
            fr / rid / "decorated_schema.json",
            fr / rid / "schema.json",
            fr / rid / "contract.json",
            fr / rid / "schema_decorated.json",
        ]
        cands += [
            root / "schema" / f"{rid}.json",
        ]

    # latest pointer style
    cands += [
        root / "schema" / "latest.json",
        root / "schema" / "latest_decorated.json",
    ]
    return cands


def _resolve_schema_payload(run_id: str | None = None) -> dict[str, Any]:
    """
    Best-effort resolver:
      1) Try runtime/state artifacts (if present).
      2) Fallback to repo schema files.
    """
    # 1) If we have no run_id, try to read findings/latest.json and use that.
    rid = _safe_run_id(run_id or "")
    if not rid:
        latest = _read_json(_findings_root() / "latest.json")
        rid2 = str(latest.get("run_id") or "").strip()
        rid = _safe_run_id(rid2)

    # 2) Try runtime candidates.
    for cand in _runtime_schema_candidates(rid):
        if not cand.exists():
            continue
        obj = _read_json(cand)
        if obj.get("ok") is False and obj.get("error") == "not_found":
            continue

        # Special case: schema/latest.json is a pointer, not the contract itself.
        if cand.name == "latest.json" and isinstance(obj, dict) and obj.get("run_id"):
            rid3 = _safe_run_id(str(obj.get("run_id") or ""))
            if rid3:
                # Try a sibling schema file by run id.
                p2 = cand.parent / f"{rid3}.json"
                if p2.exists():
                    obj2 = _read_json(p2)
                    return {"ok": True, "run_id": rid3, "path": str(p2), "contract": obj2}
            return {"ok": True, "run_id": obj.get("run_id"), "path": str(cand), "contract": obj}

        return {"ok": True, "run_id": rid, "path": str(cand), "contract": obj}

    # 3) Repo fallback
    for cand in _repo_schema_candidates():
        if cand.exists():
            obj = _read_json(cand)
            return {"ok": True, "run_id": rid, "path": str(cand), "contract": obj, "source": "repo_fallback"}

    return {"ok": False, "error": "no_schema_found"}


@router.get("/views/tactical/schema/latest")
def api_llm_tactical_schema_latest() -> dict[str, Any]:
    return _resolve_schema_payload(None)


@router.get("/views/tactical/schema/run/{run_id}")
def api_llm_tactical_schema_run(run_id: str) -> dict[str, Any]:
    rid = _safe_run_id(run_id)
    if not rid:
        return {"ok": False, "error": "bad_run_id", "run_id": run_id}
    return _resolve_schema_payload(rid)
