from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from takctl.config import load_config
from takctl.infra.db import DB


# Keep it bounded so snapshots are safe to log and fast to collect
MAX_TABLES = 30
MAX_SCHEMA_TABLES = 8


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_int(x: Any) -> int | None:
    try:
        # pg reltuples can come back as float-ish
        return int(float(x))
    except Exception:
        return None


@dataclass(frozen=True)
class TacticalSnapshotBuilder:
    def collect(self) -> dict[str, Any]:
        cfg = load_config()
        # Force psycopg2 mode for snapshot collection.
        cfg.db_mode = "psycopg2"

        db = DB(cfg)

        out: dict[str, Any] = {
            "schema_version": "taks.snapshot.tactical.v1",
            "ts_utc": _now_utc_iso(),
            "host": {"hostname": cfg.hostname},
            "postgres": {
                "meta": {},
                "discovery": {},
                "schema": {"ok": True, "tables": []},
                "notes": [
                    "Snapshot is discovery-driven and bounded (safe to log).",
                    "No LLM iteration or SQL tool loop here; this is deterministic input only.",
                ],
            },
        }

        # --- DB meta (best-effort) ---
        try:
            dbname = db.scalar("select current_database();")
            version = db.scalar("select version();")
            out["postgres"]["meta"] = {"ok": True, "database": dbname, "version": version}
        except Exception as e:
            out["postgres"]["meta"] = {"ok": False, "error": f"{type(e).__name__}: {e}"}
            # If meta fails, discovery will likely fail too, but continue best-effort.

        # --- Table discovery (bounded) ---
        discovery_sql = """
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
SELECT schema, table, est_rows, bytes
FROM cand
ORDER BY bytes DESC NULLS LAST
LIMIT %s;
"""
        tables: list[dict[str, Any]] = []
        try:
            rows = db.fetchall(discovery_sql, (MAX_TABLES,))
            for schema, table, est_rows, bytes_ in rows:
                tables.append(
                    {
                        "schema": str(schema),
                        "table": str(table),
                        "fq": f"{schema}.{table}",
                        "est_rows": _safe_int(est_rows),
                        "bytes": _safe_int(bytes_),
                    }
                )
            out["postgres"]["discovery"] = {"ok": True, "tables": tables}
        except Exception as e:
            out["postgres"]["discovery"] = {"ok": False, "error": f"{type(e).__name__}: {e}"}
            return out  # nothing more we can do safely

        # --- Schema for top tables (bounded, safe, no dynamic identifiers) ---
        schema_tables: list[dict[str, Any]] = []
        cols_sql = """
SELECT
  column_name,
  data_type,
  udt_name,
  is_nullable
FROM information_schema.columns
WHERE table_schema = %s
  AND table_name = %s
ORDER BY ordinal_position
LIMIT 200;
"""
        for t in tables[:MAX_SCHEMA_TABLES]:
            try:
                rows = db.fetchall(cols_sql, (t["schema"], t["table"]))
                cols = [
                    {
                        "column_name": str(col_name),
                        "data_type": str(data_type),
                        "udt_name": str(udt_name),
                        "is_nullable": str(is_nullable),
                    }
                    for col_name, data_type, udt_name, is_nullable in rows
                ]
                schema_tables.append(
                    {
                        "schema": t["schema"],
                        "table": t["table"],
                        "fq": t["fq"],
                        "columns": cols,
                    }
                )
            except Exception as e:
                schema_tables.append(
                    {
                        "schema": t["schema"],
                        "table": t["table"],
                        "fq": t["fq"],
                        "error": f"{type(e).__name__}: {e}",
                    }
                )

        out["postgres"]["schema"] = {"ok": True, "tables": schema_tables}
        return out
