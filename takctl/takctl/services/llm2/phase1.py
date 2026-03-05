from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from takctl.services.llm2.db import run_sql
from takctl.services.llm2.domain_config import load_domain_config
from takctl.services.llm2.paths import domains_root, runs_root, latest_root
from takctl.services.llm2.store import write_json


def _utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def run_phase1(*, run_id: str) -> dict[str, Any]:
    dom_root = domains_root()
    out: dict[str, Any] = {"ok": True, "run_id": run_id, "phase": "phase1", "domains": []}

    for ddir in sorted([p for p in dom_root.iterdir() if p.is_dir()]):
        t_dom0 = time.time()
        dom_name = ddir.name
        dom_entry: dict[str, Any] = {"domain": dom_name, "ok": True, "queries": [], "errors": []}

        try:
            cfg = load_domain_config(ddir)
            if not cfg.enabled:
                dom_entry["skipped"] = True
                out["domains"].append(dom_entry)
                continue

            sql_rel = cfg.phase1.sql_dir or "sql/phase1"
            sql_dir = ddir / sql_rel
            if not sql_dir.exists():
                dom_entry["ok"] = False
                dom_entry["errors"].append(f"missing_sql_dir: {sql_dir}")
                out["domains"].append(dom_entry)
                continue

            # -------------------------
            # Evidence (for Phase2): MINIMAL, no noise.
            # Trace (for debugging): full detail.
            # -------------------------
            evidence: dict[str, Any] = {
                "domain": dom_name,
                "ok": True,
                "phase": "phase1",
                "generated_utc": _utc_iso(),
                "queries": [],
            }
            trace: dict[str, Any] = {"ok": True, "domain": dom_name, "phase": "phase1", "items": []}

            for sp in sorted(sql_dir.glob("*.sql")):
                name = sp.stem
                trace_item: dict[str, Any] = {"name": name, "path": str(sp)}

                try:
                    sql = sp.read_text(encoding="utf-8")
                except Exception as e:
                    msg = f"read_failed: {type(e).__name__}: {e}"
                    trace_item.update({"ok": False, "error": msg})
                    trace["items"].append(trace_item)
                    dom_entry["queries"].append({"name": name, "ok": False, "error": msg})
                    evidence["ok"] = False
                    evidence["queries"].append({"name": name, "columns": None, "rows": None, "error": msg})
                    continue

                r = run_sql(sql)
                trace_item.update(
                    {
                        "ok": bool(r.ok),
                        "elapsed_ms": r.elapsed_ms,
                        "rowcount": r.rowcount,
                        "columns": r.columns,
                        "rows": r.rows,
                        "error": r.error,
                    }
                )
                trace["items"].append(trace_item)
                dom_entry["queries"].append(
                    {"name": name, "ok": bool(r.ok), "elapsed_ms": r.elapsed_ms, "rowcount": r.rowcount, "error": r.error}
                )

                # Minimal evidence item
                ev_item: dict[str, Any] = {"name": name, "columns": r.columns, "rows": r.rows}
                if not r.ok:
                    evidence["ok"] = False
                    ev_item["error"] = r.error
                evidence["queries"].append(ev_item)

            # write run artifacts
            run_dir = runs_root() / run_id / dom_name / "phase1"
            write_json(run_dir / "evidence.json", evidence)
            write_json(run_dir / "trace.json", trace)

            # write latest pointers for domain/phase
            latest_dir = latest_root() / dom_name / "phase1"
            write_json(latest_dir / "latest.json", evidence)
            write_json(latest_dir / "trace.json", trace)

        except Exception as e:
            dom_entry["ok"] = False
            dom_entry["errors"].append(f"domain_failed: {type(e).__name__}: {e}")

        dom_entry["elapsed_ms"] = int((time.time() - t_dom0) * 1000)
        out["domains"].append(dom_entry)

    return out
