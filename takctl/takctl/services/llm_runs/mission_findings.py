#!/usr/bin/env python3
"""
Deterministic mission findings runner that writes:
- debug_state.json (phase markers)
- trace.json (fold-out execution trace for UI)
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict

# --- WRITE_FINDINGS_RUN_DIR_AND_POINTER -------------------------------------
def _write_atomic(path: Path, text: str, mode: int = 0o664) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.chmod(mode)
    tmp.replace(path)


def _write_findings_run_file(out_dir: Path, name: str, obj: Any) -> None:
    safe = "".join(c for c in (name or "").strip() if c.isalnum() or c in ("-", "_", ".", "@"))
    if not safe:
        safe = "artifact.json"
    if "." not in safe:
        safe = safe + ".json"
    _write_atomic(out_dir / safe, json.dumps(obj, ensure_ascii=False, indent=2))


def _write_findings_latest(out_root: Path, run_id: str, out_dir: Path) -> None:
    latest = {
        "run_id": run_id,
        "generated_utc": _utc_ts_iso(),
        "out_dir": str(out_dir),
    }
    _write_atomic(out_root / "latest.json", json.dumps(latest, ensure_ascii=False, indent=2))
# ---------------------------------------------------------------------------

from takctl.services.llm_introspection import write_state, append_event, write_artifact_text

# --- SANITIZE_TRACE_PREVIEW_GROUPS ------------------------------------------
def _shorten_str(v: str, keep: int = 200) -> str:
    if v is None:
        return v
    v = str(v)
    if len(v) <= keep:
        return v
    return v[:keep] + f"…(len={len(v)})"


def _sanitize_obj(x: Any) -> Any:
    # Keep trace JSON small and UI-safe.
    if isinstance(x, dict):
        out = {}
        for k, v in x.items():
            kk = str(k)
            if kk in ("groups", "group") and isinstance(v, str):
                out[kk] = _shorten_str(v, keep=32)  # bitmask -> tiny
            elif isinstance(v, str):
                out[kk] = _shorten_str(v, keep=200)
            else:
                out[kk] = _sanitize_obj(v)
        return out
    if isinstance(x, list):
        return [_sanitize_obj(v) for v in x]
    if isinstance(x, str):
        return _shorten_str(x, keep=200)
    return x
# ---------------------------------------------------------------------------

BASE_STATE = Path("/opt/tak/tools/takctl/state/llm/tactical-operations")
BASELINE_LATEST = BASE_STATE / "baseline" / "latest_bundle.json"
OUT_ROOT = BASE_STATE / "findings"
VIEW = "tactical-operations"
def _utc_ts_compact() -> str:
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


def _utc_ts_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_results(results_dir: Path) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for p in sorted(results_dir.glob("*.json")):
        if p.name.endswith(".error.json"):
            continue
        name = p.name.rsplit(".", 1)[0]
        out[name] = _read_json(p)
    return out


def main() -> int:
    run_id = _utc_ts_compact()
    out_dir = OUT_ROOT / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    write_state(VIEW, phase="findings_started", stage="findings", run_id=run_id, iteration=None)
    append_event(VIEW, event="findings_started", stage="findings", run_id=run_id, iteration=None)

    if not BASELINE_LATEST.exists():
        write_state(VIEW, phase="error", stage="findings", run_id=run_id, error=f"missing {BASELINE_LATEST}")
        append_event(VIEW, event="error", stage="findings", run_id=run_id, error=f"missing {BASELINE_LATEST}")
        return 1

    bundle = _read_json(BASELINE_LATEST)
    results_dir = Path(bundle["results_dir"])
    sql_dir = Path(bundle["sql_dir"])
    results = _load_results(results_dir)

    write_state(
        VIEW,
        phase="baseline_loaded",
        stage="findings",
        run_id=run_id,
        baseline_run_id=bundle.get("run_id"),
        results_dir=str(results_dir),
    )
    append_event(
        VIEW,
        event="baseline_loaded",
        stage="findings",
        run_id=run_id,
        baseline_run_id=bundle.get("run_id"),
    )

    trace: Dict[str, Any] = {
        "run_id": run_id,
        "generated_utc": _utc_ts_iso(),
        "stages": [
            {
                "stage": "baseline",
                "baseline_run_id": bundle.get("run_id"),
                "queries": [
                    {
                        "name": name,
                        "sql": (sql_dir / f"{name}.sql").read_text(encoding="utf-8") if (sql_dir / f"{name}.sql").exists() else f"(missing sql file: {name}.sql)",
                        "result_preview": _sanitize_obj(blob),
                        "row_count": len((blob or {}).get("rows", []) if isinstance(blob, dict) else []),
                    }
                    for name, blob in results.items()
                ],
            },
            {
                "stage": "findings",
                "summary": {
                    "queries_loaded": len(results),
                    "note": "LLM stage not wired yet; this is deterministic aggregation only.",
                },
            },
        ],
    }

    write_artifact_text(VIEW, "trace.json", json.dumps(trace, indent=2))
    write_artifact_text(VIEW, "baseline_latest_bundle.json", json.dumps(bundle, indent=2))

    # Also persist deterministic outputs under findings/<run_id>/ for run browsing + pointers.
    _write_findings_run_file(out_dir, "trace.json", trace)
    _write_findings_run_file(out_dir, "baseline_latest_bundle.json", bundle)
    _write_findings_latest(OUT_ROOT, run_id, out_dir)

    write_state(VIEW, phase="findings_complete", stage="findings", run_id=run_id)
    append_event(VIEW, event="findings_complete", stage="findings", run_id=run_id)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
