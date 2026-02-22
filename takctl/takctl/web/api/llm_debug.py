from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

from takctl.services.llm_introspection import (
    list_artifacts,
    read_artifact,
    state_root,
    tail_events,
)

router = APIRouter(prefix="/api/llm/views/tactical/debug", tags=["llm-debug"])

_CANON = "tactical-operations"


def _require_view(view: Optional[str]) -> str:
    v = (view or "").strip()
    if not v:
        return _CANON
    if v != _CANON:
        raise HTTPException(status_code=400, detail=f"invalid_view: {v} (only '{_CANON}' supported)")
    return v


def _mtime_iso(p: Path) -> str:
    try:
        st = p.stat()
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(st.st_mtime))
    except Exception:
        return ""


def _read_text(p: Path, limit: int = 256_000) -> str:
    try:
        txt = p.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        return f"read_failed: {e}"
    if len(txt) > limit:
        return txt[:limit] + "\n…(truncated)\n"
    return txt


def _try_parse_json(txt: str) -> Optional[Any]:
    try:
        return json.loads(txt)
    except Exception:
        return None


def _file_info(root: Path, rel: str) -> dict[str, Any]:
    p = root / rel
    if not p.exists() or not p.is_file():
        return {"exists": False, "path": str(p)}
    try:
        st = p.stat()
        return {
            "exists": True,
            "path": str(p),
            "bytes": st.st_size,
            "mtime_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(st.st_mtime)),
        }
    except Exception as e:
        return {"exists": True, "path": str(p), "error": str(e)}


@router.get("/state")
def get_state(view: Optional[str] = None, raw: int = 0) -> dict:
    v = _require_view(view)
    root = state_root(v)
    p = root / "debug_state.json"
    if not p.exists():
        return {"ok": False, "view": v, "error": "no_state_yet"}

    txt = _read_text(p)
    if raw:
        return {"ok": True, "view": v, "raw_text": txt}

    parsed = _try_parse_json(txt)
    return {
        "ok": True,
        "view": v,
        "state": parsed if parsed is not None else None,
        "raw_text": txt,
        "mtime_utc": _mtime_iso(p),
    }


@router.get("/events")
def get_events(view: Optional[str] = None, tail: int = 200) -> dict:
    v = _require_view(view)
    tail = max(1, min(int(tail), 2000))
    return {"ok": True, "view": v, "events": tail_events(v, tail=tail)}


@router.get("/artifacts")
def get_artifacts(view: Optional[str] = None) -> dict:
    v = _require_view(view)
    return {"ok": True, "view": v, "artifacts": list_artifacts(v)}


@router.get("/artifact/{name}")
def get_artifact(name: str, view: Optional[str] = None):
    v = _require_view(view)
    p, meta = read_artifact(v, name)
    if not p:
        raise HTTPException(status_code=404, detail="artifact_not_found")
    txt = p.read_text(encoding="utf-8", errors="ignore")
    return PlainTextResponse(content=txt, media_type="text/plain; charset=utf-8")


@router.get("/timeline")
def get_timeline(view: Optional[str] = None, tail: int = 200) -> dict:
    v = _require_view(view)
    root = state_root(v)

    state_p = root / "debug_state.json"
    state_txt = _read_text(state_p) if state_p.exists() else ""
    state_obj = _try_parse_json(state_txt) if state_txt else None

    tail = max(1, min(int(tail), 2000))
    events = tail_events(v, tail=tail)
    artifacts = list_artifacts(v)

    known = {
        "debug_state.json": _file_info(root, "debug_state.json"),
        "debug_events.jsonl": _file_info(root, "debug_events.jsonl"),
        "latest.json": _file_info(root, "latest.json"),
        "snapshot.json": _file_info(root, "snapshot.json"),
        "last_run.json": _file_info(root, "last_run.json"),
        "baseline/latest_bundle.json": _file_info(root, "baseline/latest_bundle.json"),
        "findings/latest.json": _file_info(root, "findings/latest.json"),
    }

    return {
        "ok": True,
        "view": v,
        "state": state_obj,
        "state_raw_text": state_txt if state_txt else None,
        "events": events,
        "artifacts": artifacts,
        "known_files": known,
        "root": str(root),
    }

# -----------------------------------------------------------------------------
# Phase 0 summary (deterministic SQL + results, NO ROWS)
# -----------------------------------------------------------------------------
@router.get("/phase0/latest", include_in_schema=False)
def phase0_latest() -> dict:
    """
    UX-shaped Phase 0 payload:
      - what SQL was executed (from baseline sql_dir)
      - whether each query succeeded
      - rowcount + elapsed_ms
      - NO preview rows
    """
    import json
    from pathlib import Path

    base = Path("/opt/tak/tools/takctl/state/llm/tactical-operations")
    bundle_path = base / "baseline" / "latest_bundle.json"

    if not bundle_path.exists():
        return {"ok": False, "error": f"missing baseline bundle: {bundle_path}"}

    try:
        bundle = json.loads(bundle_path.read_text("utf-8"))
    except Exception as e:
        return {"ok": False, "error": f"failed to read {bundle_path}: {type(e).__name__}: {e}"}

    sql_dir = Path(bundle.get("sql_dir") or "")
    results_dir = Path(bundle.get("results_dir") or "")

    if not sql_dir.exists():
        return {"ok": False, "error": f"missing sql_dir: {sql_dir}", "bundle": bundle}
    if not results_dir.exists():
        return {"ok": False, "error": f"missing results_dir: {results_dir}", "bundle": bundle}

    queries = []
    for p in sorted(sql_dir.glob("*.sql")):
        name = p.stem

        # SQL text (kept; UI will collapse by default)
        try:
            sql = p.read_text("utf-8")
        except Exception as e:
            sql = f"(failed to read {p}: {type(e).__name__}: {e})"

        # Result summary (no rows)
        res_path = results_dir / f"{name}.json"
        ok = None
        rowcount = None
        elapsed_ms = None
        error = None
        columns = None

        if res_path.exists():
            try:
                r = json.loads(res_path.read_text("utf-8"))
                ok = bool(r.get("ok")) if ("ok" in r) else None
                rowcount = r.get("rowcount")
                elapsed_ms = r.get("elapsed_ms")
                error = r.get("error")
                columns = r.get("columns")
            except Exception as e:
                ok = False
                error = f"failed to read {res_path}: {type(e).__name__}: {e}"
        else:
            ok = False
            error = f"missing result: {res_path}"

        queries.append({
            "name": name,
            "sql": sql,
            "ok": ok,
            "rowcount": rowcount,
            "elapsed_ms": elapsed_ms,
            "error": error,
            "columns": columns,
        })

    return {
        "ok": True,
        "generated_utc": bundle.get("generated_utc"),
        "baseline_run_id": bundle.get("run_id"),
        "sql_dir": str(sql_dir),
        "results_dir": str(results_dir),
        "queries": queries,
    }
