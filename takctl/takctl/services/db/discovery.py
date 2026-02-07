from __future__ import annotations

from typing import Any, Optional

from takctl.services.db.client import DB


# -----------------------------------------------------------------------------
# Schema discovery
# -----------------------------------------------------------------------------

def discover_tables(db: DB, limit: int = 30) -> dict[str, Any]:
    """
    Discover tables that *might* contain tactical data using name heuristics.

    Returns:
      {
        "ok": bool,
        "tables": [
          {
            "schema": str,
            "table": str,
            "fq_table": str,
            "est_rows": int | None,
            "bytes": int | None,
          },
          ...
        ]
      }
    """
    sql = """
    SELECT
      n.nspname       AS schema,
      c.relname       AS table,
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
    ORDER BY pg_total_relation_size(c.oid) DESC
    LIMIT %s;
    """

    try:
        rows = db.query(sql, (limit,))
    except Exception as e:
        return {"ok": False, "error": str(e)}

    out = []
    for r in rows:
        out.append(
            {
                "schema": r["schema"],
                "table": r["table"],
                "fq_table": f"{r['schema']}.{r['table']}",
                "est_rows": r.get("est_rows"),
                "bytes": r.get("bytes"),
            }
        )

    return {"ok": True, "tables": out}


# -----------------------------------------------------------------------------
# Column discovery
# -----------------------------------------------------------------------------

def discover_timestamp_columns(
    db: DB,
    schema: str,
    table: str,
    limit: int = 3,
) -> list[str]:
    """
    Find timestamp/date-like columns in a table.

    Preference is given (heuristically) to columns named like:
      created, last, time, ts, date
    """
    sql = """
    SELECT
      column_name
    FROM information_schema.columns
    WHERE table_schema = %s
      AND table_name = %s
      AND data_type IN (
        'timestamp without time zone',
        'timestamp with time zone',
        'date'
      )
    ORDER BY ordinal_position;
    """

    try:
        rows = db.query(sql, (schema, table))
    except Exception:
        return []

    cols = [r["column_name"] for r in rows]

    def _score(name: str) -> tuple[int, str]:
        lname = name.lower()
        if any(k in lname for k in ("created", "last", "time", "ts", "date")):
            return (0, name)
        return (1, name)

    cols.sort(key=_score)
    return cols[:limit]


# -----------------------------------------------------------------------------
# Activity probing
# -----------------------------------------------------------------------------

def probe_latest_activity(
    db: DB,
    fq_table: str,
    columns: list[str],
) -> dict[str, Any]:
    """
    For a given table and a small set of timestamp columns,
    probe max(column) for each column.

    Safe, cheap, read-only.
    """
    if "." not in fq_table:
        return {"table": fq_table, "error": "invalid table name"}

    schema, table = fq_table.split(".", 1)

    latest: dict[str, Any] = {"table": fq_table, "latest": {}}

    for col in columns:
        sql = f"SELECT max({col}) AS value FROM {schema}.{table};"
        try:
            value = db.scalar(sql)
            latest["latest"][col] = value
        except Exception as e:
            latest["latest"][col] = {"error": str(e)}

    return latest


def top_active_tables(
    db: DB,
    discovered: list[dict[str, Any]],
    limit: int = 8,
) -> list[dict[str, Any]]:
    """
    For the top-N discovered tables, attempt to probe recent activity.
    """
    out: list[dict[str, Any]] = []

    for t in discovered[:limit]:
        fq = t.get("fq_table")
        if not fq or "." not in fq:
            continue

        schema, table = fq.split(".", 1)
        cols = discover_timestamp_columns(db, schema, table)

        if not cols:
            out.append(
                {
                    "table": fq,
                    "note": "no timestamp/date columns detected",
                }
            )
            continue

        out.append(probe_latest_activity(db, fq, cols))

    return out


# -----------------------------------------------------------------------------
# DB metadata
# -----------------------------------------------------------------------------

def db_meta(db: DB) -> dict[str, Any]:
    """
    Lightweight DB identity metadata.
    """
    try:
        row = db.query_one("SELECT current_database() AS db, version() AS version;")
        if not row:
            return {"ok": False, "error": "no result"}
        return {
            "ok": True,
            "database": row.get("db"),
            "version": row.get("version"),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}

