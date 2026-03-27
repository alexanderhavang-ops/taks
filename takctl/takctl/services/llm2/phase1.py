from __future__ import annotations

import importlib.util
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from takctl.services.llm2.db import run_sql
from takctl.services.llm2.domain_config import load_domain_config
from takctl.services.llm2.paths import domains_root, runs_root, latest_root
from takctl.services.llm2.store import write_json
from takctl.config_store import load_runtime_config_view


def _utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _phase_cfg_value(phase_cfg: Any, key: str, default: Any = None) -> Any:
    if phase_cfg is None:
        return default
    if isinstance(phase_cfg, dict):
        return phase_cfg.get(key, default)
    return getattr(phase_cfg, key, default)


def _load_enrich_hook(domain_dir: Path, rel_path: str) -> Optional[Callable[..., dict[str, Any]]]:
    p = (domain_dir / rel_path).resolve()
    if not p.exists():
        raise RuntimeError(f"missing_enrich_hook: {p}")

    mod_name = f"llm2_enrich_{domain_dir.name}_{p.stem}_{int(p.stat().st_mtime_ns)}"
    spec = importlib.util.spec_from_file_location(mod_name, str(p))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable_to_load_enrich_spec: {p}")

    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    enrich = getattr(mod, "enrich", None)
    if not callable(enrich):
        raise RuntimeError(f"enrich_hook_missing_callable_enrich: {p}")

    return enrich


def _render_sql_vars(sql: str, *, phase_cfg: Any) -> str:
    cfg = load_runtime_config_view()
    sql_vars = _phase_cfg_value(phase_cfg, "sql_vars", {}) or {}
    if not isinstance(sql_vars, dict):
        return sql

    out = str(sql)

    for var_name, spec in sql_vars.items():
        token = "{{" + str(var_name) + "}}"

        default = None
        config_key = None

        if isinstance(spec, dict):
            config_key = str(spec.get("config_key") or "").strip() or None
            default = spec.get("default")
        else:
            default = spec

        raw = None
        if config_key:
            raw = cfg.get(config_key, "")

        if raw is None or str(raw).strip() == "":
            raw = default

        if raw is None:
            raise RuntimeError(f"sql_var_unresolved:{var_name}")

        val = str(raw).strip()

        if not re.fullmatch(r"-?\d+", val):
            raise RuntimeError(f"sql_var_not_int:{var_name}={val}")

        out = out.replace(token, val)

    return out


def run_phase1(*, run_id: str, domain: str | None = None) -> dict[str, Any]:
    dom_root = domains_root()
    requested_domain = (domain or "").strip()

    out: dict[str, Any] = {
        "ok": True,
        "run_id": run_id,
        "phase": "phase1",
        "domain": requested_domain or "all",
        "domains": [],
    }

    domain_dirs = sorted([p for p in dom_root.iterdir() if p.is_dir()])
    if requested_domain:
        domain_dirs = [p for p in domain_dirs if p.name == requested_domain]
        if not domain_dirs:
            return {
                "ok": False,
                "run_id": run_id,
                "phase": "phase1",
                "domain": requested_domain,
                "error": f"unknown_domain: {requested_domain}",
                "domains": [],
            }

    infra_dir = dom_root.parent

    for ddir in domain_dirs:
        t_dom0 = time.time()
        dom_name = ddir.name
        dom_entry: dict[str, Any] = {"domain": dom_name, "ok": True, "queries": [], "errors": []}

        try:
            cfg = load_domain_config(infra_dir, dom_name)
            if not bool(cfg.get("enabled", True)):
                dom_entry["skipped"] = True
                out["domains"].append(dom_entry)
                continue

            phase1_cfg = (cfg.get("phases") or {}).get("phase1") or {}
            sql_rel = _phase_cfg_value(phase1_cfg, "sql_dir", "sql/phase1") or "sql/phase1"
            sql_dir = ddir / str(sql_rel)

            evidence: dict[str, Any] = {
                "domain": dom_name,
                "ok": True,
                "phase": "phase1",
                "generated_utc": _utc_iso(),
                "queries": [],
            }
            trace: dict[str, Any] = {"ok": True, "domain": dom_name, "phase": "phase1", "items": []}

            if sql_dir.exists():
                for sp in sorted(sql_dir.glob("*.sql")):
                    name = sp.stem
                    trace_item: dict[str, Any] = {"name": name, "path": str(sp)}

                    try:
                        sql = sp.read_text(encoding="utf-8")
                        sql = _render_sql_vars(sql, phase_cfg=phase1_cfg)
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

                    ev_item: dict[str, Any] = {"name": name, "columns": r.columns, "rows": r.rows}
                    if not r.ok:
                        evidence["ok"] = False
                        ev_item["error"] = r.error
                    evidence["queries"].append(ev_item)
            else:
                trace["sql_dir"] = str(sql_dir)
                trace["sql_dir_exists"] = False
                evidence["queries"] = []

            phase1_enrich_rel = _phase_cfg_value(phase1_cfg, "enrich", None)
            if phase1_enrich_rel:
                try:
                    enrich = _load_enrich_hook(ddir, str(phase1_enrich_rel))
                    evidence = enrich(evidence) or evidence
                    trace["enrich"] = {"ok": True, "path": str((ddir / str(phase1_enrich_rel)).resolve())}
                except Exception as e:
                    evidence["ok"] = False
                    trace["ok"] = False
                    trace["enrich"] = {
                        "ok": False,
                        "error": f"{type(e).__name__}: {e}",
                        "path": str(ddir / str(phase1_enrich_rel)),
                    }
                    dom_entry["ok"] = False
                    dom_entry["errors"].append(f"phase1_enrich_failed: {type(e).__name__}: {e}")

            run_dir = runs_root() / run_id / dom_name / "phase1"
            write_json(run_dir / "evidence.json", evidence)
            write_json(run_dir / "trace.json", trace)

            latest_dir = latest_root() / dom_name / "phase1"
            write_json(latest_dir / "latest.json", evidence)
            write_json(latest_dir / "trace.json", trace)

        except Exception as e:
            dom_entry["ok"] = False
            dom_entry["errors"].append(f"domain_failed: {type(e).__name__}: {e}")

        dom_entry["elapsed_ms"] = int((time.time() - t_dom0) * 1000)
        out["domains"].append(dom_entry)

    if any(not bool(d.get("ok", False)) for d in out["domains"]):
        out["ok"] = False

    return out
