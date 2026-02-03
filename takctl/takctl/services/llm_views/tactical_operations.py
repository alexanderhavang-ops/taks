from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional


def _run(cmd: list[str], timeout: int = 5) -> tuple[int, str]:
    try:
        p = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
            check=False,
        )
        return int(p.returncode), (p.stdout or "").strip()
    except Exception as e:
        return 1, f"{type(e).__name__}: {e}"


def _psql(sql: str, db: str = "cot") -> tuple[int, str]:
    # Best-effort. Works if local auth allows it (often does on TAK nodes).
    # If it fails, we still return a structured error in the snapshot.
    return _run(["psql", "-d", db, "-At", "-c", sql], timeout=6)


def _parse_kv_lines(out: str) -> dict[str, str]:
    d: dict[str, str] = {}
    for line in out.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            d[k.strip()] = v.strip()
    return d


def _discover_tables() -> dict[str, Any]:
    """
    Discovery approach:
      - find tables whose names suggest tactical content (chat, mission, cot, track, event, log)
      - include size/row estimate from pg_class
    """
    sql = r"""
WITH cand AS (
  SELECT
    n.nspname AS schema,
    c.relname AS table,
    c.reltuples::bigint AS est_rows,
    pg_total_relation_size(c.oid) AS bytes
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE c.relkind = 'r'
    AND n.nspname NOT IN ('pg_catalog','information_schema')
    AND (
      c.relname ILIKE '%chat%' OR
      c.relname ILIKE '%mission%' OR
      c.relname ILIKE '%cot%' OR
      c.relname ILIKE '%track%' OR
      c.relname ILIKE '%event%' OR
      c.relname ILIKE '%log%' OR
      c.relname ILIKE '%message%'
    )
)
SELECT schema || '.' || table
  || '|' || est_rows
  || '|' || bytes
FROM cand
ORDER BY bytes DESC
LIMIT 30;
"""
    code, out = _psql(sql)
    if code != 0:
        return {"ok": False, "error": out}

    rows = []
    for line in out.splitlines():
        parts = line.split("|")
        if len(parts) != 3:
            continue
        fq, est, b = parts
        def _i(x: str) -> Optional[int]:
            try:
                return int(float(x))
            except Exception:
                return None
        rows.append({
            "table": fq,
            "est_rows": _i(est),
            "bytes": _i(b),
        })
    return {"ok": True, "tables": rows}


def _discover_timestamp_columns(fq_table: str) -> list[str]:
    # Return timestamp-ish columns in a table, to allow "latest activity" probing.
    # fq_table is schema.table
    schema, table = fq_table.split(".", 1)
    sql = f"""
SELECT column_name
FROM information_schema.columns
WHERE table_schema = '{schema}'
  AND table_name = '{table}'
  AND data_type IN ('timestamp without time zone','timestamp with time zone','date')
ORDER BY ordinal_position;
"""
    code, out = _psql(sql)
    if code != 0:
        return []
    cols = [c.strip() for c in out.splitlines() if c.strip()]
    # Heuristic preference: created/last/ts/time
    cols.sort(key=lambda c: (0 if re.search(r"(created|last|time|ts|date)", c, re.I) else 1, c))
    return cols[:3]


def _probe_latest(fq_table: str, cols: list[str]) -> dict[str, Any]:
    schema, table = fq_table.split(".", 1)

    # Lightweight: only do max() for 1-3 cols, each separately.
    latest: dict[str, Any] = {"table": fq_table, "latest": {}}
    for col in cols:
        sql = f"SELECT max({col}) FROM {schema}.{table};"
        code, out = _psql(sql)
        if code != 0:
            latest["latest"][col] = {"error": out}
        else:
            latest["latest"][col] = (out.strip() or None)
    return latest


def _top_active_tables(tables: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    For the top few candidate tables, probe for latest timestamps where possible.
    Keep it fast and safe.
    """
    out: list[dict[str, Any]] = []
    for t in tables[:8]:
        fq = t.get("table") or ""
        if "." not in fq:
            continue
        cols = _discover_timestamp_columns(fq)
        if not cols:
            out.append({"table": fq, "note": "no timestamp/date columns detected"})
            continue
        out.append(_probe_latest(fq, cols))
    return out


def _db_meta() -> dict[str, Any]:
    code, out = _psql("SELECT current_database() || '|' || version();")
    if code != 0:
        return {"ok": False, "error": out}
    parts = out.split("|", 1)
    return {"ok": True, "database": parts[0] if parts else None, "version": parts[1] if len(parts) > 1 else None}


@dataclass(frozen=True)
class TacticalInputsSnapshot:
    def collect(self) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()

        meta = _db_meta()
        tables_info = _discover_tables()

        latest_probes: list[dict[str, Any]] = []
        if tables_info.get("ok") and isinstance(tables_info.get("tables"), list):
            latest_probes = _top_active_tables(tables_info["tables"])

        return {
            "ts_utc": now,
            "host": {
                "hostname": os.uname().nodename,
            },
            "postgres": {
                "meta": meta,
                "discovery": tables_info,
                "latest_activity_probes": latest_probes,
                "notes": [
                    "This is schema-discovery driven (no hard dependency on known TAK DB schema).",
                    "Later we will add explicit extraction for chats/missions/units when schema is confirmed.",
                ],
            },
        }
