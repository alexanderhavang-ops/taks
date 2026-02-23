from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Optional

def _utc_iso(ts: int | None = None) -> str:
    if ts is None:
        ts = int(time.time())
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))

def _q_by_name(results: List[dict[str, Any]], name: str) -> Optional[dict[str, Any]]:
    for q in results:
        if str(q.get("name") or "") == name:
            return q
    return None

def _first_ts(q: dict[str, Any] | None, key: str) -> str | None:
    if not q or not q.get("ok") or not isinstance(q.get("rows"), list) or not q["rows"]:
        return None
    v = q["rows"][0].get(key)
    return str(v) if v not in (None, "") else None

def build_ops_brief(*, results: List[dict[str, Any]], run_id: str) -> dict[str, Any]:
    q_m = _q_by_name(results, "10_mission_list")
    q_i = _q_by_name(results, "30_invitations")
    q_c = _q_by_name(results, "40_changes_timeline")

    latest_ts = _first_ts(q_c, "ts") or _first_ts(q_i, "create_time") or _first_ts(q_m, "create_time")
    latest_name = None
    try:
        if q_m and q_m.get("ok") and q_m.get("rows"):
            latest_name = str(q_m["rows"][0].get("name") or "") or None
    except Exception:
        pass

    row_counts = {str(q.get("name") or ""): int(q.get("row_count") or 0) for q in results if isinstance(q, dict)}

    ops_brief: dict[str, Any] = {
        "contract": {"name": "taks.ops_brief", "version": 1},
        "bounds": {"max_entities": 10, "max_events": 25},
        "signals": {
            "row_counts": row_counts,
            "latest_ts": latest_ts,
            "latest_name": latest_name,
        },
        "evidence": {
            "missions_head": (q_m.get("rows")[:8] if q_m and q_m.get("ok") and isinstance(q_m.get("rows"), list) else []),
            "changes_head": (q_c.get("rows")[:10] if q_c and q_c.get("ok") and isinstance(q_c.get("rows"), list) else []),
            "invitations_head": (q_i.get("rows")[:10] if q_i and q_i.get("ok") and isinstance(q_i.get("rows"), list) else []),
        },
        "run": {"run_id": run_id, "generated_utc": _utc_iso()},
    }
    return ops_brief

def write_phase1_artifacts(
    *,
    write_json_atomic,
    meta,
    root: Path,
    run_dir: Path,
    run_id: str,
    ops_brief: dict[str, Any],
) -> dict[str, Any]:
    """
    Writes:
      runs/<run_id>/phase1/missions_brief.json
      runs/<run_id>/phase1/trace.json
      phase1_latest.json pointer
    Returns a tiny status dict for notes/debug.
    """
    phase1_dir = run_dir / "phase1"
    phase1_latest_path = root / "phase1_latest.json"

    phase1_dir.mkdir(parents=True, exist_ok=True)
    p1_brief = phase1_dir / "missions_brief.json"
    p1_trace = phase1_dir / "trace.json"

    write_json_atomic(p1_brief, ops_brief, mode=0o644)
    write_json_atomic(
        p1_trace,
        {
            "contract": {"name": "taks.ops_brief_trace", "version": 1},
            "ok": True,
            "run_id": run_id,
            "generated_utc": _utc_iso(),
            "notes": ["built from phase0 curated queries"],
        },
        mode=0o644,
    )

    write_json_atomic(
        phase1_latest_path,
        {
            "_meta": meta(phase1_latest_path, run_id),
            "ok": True,
            "run_id": run_id,
            "generated_utc": _utc_iso(),
            "missions_brief_path": str(p1_brief),
            "trace_path": str(p1_trace),
        },
        mode=0o644,
    )

    return {
        "ok": True,
        "missions_brief_path": str(p1_brief),
        "trace_path": str(p1_trace),
        "phase1_latest_path": str(phase1_latest_path),
    }
