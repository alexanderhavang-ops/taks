from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from takctl.services.llm2.db import run_sql
from takctl.services.llm2.domain_config import load_domain_config
from takctl.services.llm2.paths import domains_root, runs_root, latest_root
from takctl.services.llm2.store import write_json


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

            # run every *.sql (crash isolated per file)
            results: dict[str, Any] = {"ok": True, "domain": dom_name, "phase": "phase1", "queries": []}
            trace: dict[str, Any] = {"ok": True, "domain": dom_name, "phase": "phase1", "items": []}

            for sp in sorted(sql_dir.glob("*.sql")):
                name = sp.stem
                item: dict[str, Any] = {"name": name, "path": str(sp)}
                try:
                    sql = sp.read_text(encoding="utf-8")
                except Exception as e:
                    item.update({"ok": False, "error": f"read_failed: {type(e).__name__}: {e}"})
                    trace["items"].append(item)
                    dom_entry["queries"].append({"name": name, "ok": False, "error": item["error"]})
                    continue

                r = run_sql(sql)
                item.update({
                    "ok": bool(r.ok),
                    "elapsed_ms": r.elapsed_ms,
                    "rowcount": r.rowcount,
                    "columns": r.columns,
                    # keep rows for now (can be dropped later); safe cap is in db.run_sql
                    "rows": r.rows,
                    "error": r.error,
                })
                trace["items"].append(item)
                dom_entry["queries"].append({"name": name, "ok": item["ok"], "elapsed_ms": r.elapsed_ms, "rowcount": r.rowcount, "error": r.error})

                results["queries"].append(item)

            # write run artifacts
            run_dir = runs_root() / run_id / dom_name / "phase1"
            write_json(run_dir / "evidence.json", results)
            write_json(run_dir / "trace.json", trace)

            # write latest pointers for domain/phase
            latest_dir = latest_root() / dom_name / "phase1"
            write_json(latest_dir / "latest.json", results)
            write_json(latest_dir / "trace.json", trace)

        except Exception as e:
            dom_entry["ok"] = False
            dom_entry["errors"].append(f"domain_failed: {type(e).__name__}: {e}")

        dom_entry["elapsed_ms"] = int((time.time() - t_dom0) * 1000)
        out["domains"].append(dom_entry)

    return out
