from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any, Optional

from takctl.config import load_config


# -----------------------------------------------------------------------------
# Policy / limits (keep conservative; tune later)
# -----------------------------------------------------------------------------

DEFAULT_STATEMENT_TIMEOUT_MS = 3000     # server-side timeout
DEFAULT_CONNECT_TIMEOUT_SEC = 3
DEFAULT_MAX_ROWS = 200
DEFAULT_MAX_CELL_CHARS = 4096          # truncate large text cells


# -----------------------------------------------------------------------------
# Safety checks
# -----------------------------------------------------------------------------

_FORBIDDEN = re.compile(
    r"(?is)\b("
    r"insert|update|delete|drop|alter|create|truncate|grant|revoke|vacuum|analyze|"
    r"copy|call|do|execute|prepare|deallocate|listen|notify|cluster|reindex|"
    r"set\s+role|set\s+session|set\s+transaction|"
    r"pg_terminate_backend|pg_cancel_backend"
    r")\b"
)

_MULTI_STMT = re.compile(r";\s*\S")  # semicolon followed by non-whitespace (multi-statement)


def _normalize_sql(sql: str) -> str:
    return (sql or "").strip().strip(";").strip()


def _is_select_only(sql: str) -> bool:
    s = _normalize_sql(sql)
    if not s:
        return False
    # Must start with SELECT / WITH (CTE)
    if not re.match(r"(?is)^(select|with)\b", s):
        return False
    # Reject forbidden keywords anywhere
    if _FORBIDDEN.search(s):
        return False
    # Reject obvious multi-statement patterns
    if _MULTI_STMT.search(s):
        return False
    return True


def _ensure_limit(sql: str, max_rows: int) -> str:
    """
    Naive but effective:
      - If query already has LIMIT, leave it.
      - Else append LIMIT max_rows.
    """
    s = _normalize_sql(sql)
    if re.search(r"(?is)\blimit\s+\d+\b", s):
        return s
    return f"{s}\nLIMIT {int(max_rows)}"


def _truncate_cell(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, (int, float, bool)):
        return v
    # psycopg2 returns many types already decoded; stringify unknowns safely
    s = str(v)
    if len(s) > DEFAULT_MAX_CELL_CHARS:
        return s[:DEFAULT_MAX_CELL_CHARS] + "…"
    return s


@dataclass
class DBQueryResult:
    ok: bool
    sql: str
    columns: list[str]
    rows: list[list[Any]]
    rowcount: int
    elapsed_ms: int
    error: Optional[str] = None
    notes: Optional[list[str]] = None


def run_readonly_query(
    sql: str,
    params: tuple[Any, ...] = (),
    *,
    statement_timeout_ms: int = DEFAULT_STATEMENT_TIMEOUT_MS,
    max_rows: int = DEFAULT_MAX_ROWS,
) -> DBQueryResult:
    """
    Read-only SQL executor for LLM tool-loop.

    - Requires SELECT/WITH only.
    - Enforces server-side statement_timeout.
    - Ensures a LIMIT if absent (bounded result size).
    - Uses takctl config/env (TAKCTL_DB_* via secrets/db.env load_config()).
    """
    t0 = time.time()

    raw = _normalize_sql(sql)
    if not _is_select_only(raw):
        return DBQueryResult(
            ok=False,
            sql=raw,
            columns=[],
            rows=[],
            rowcount=0,
            elapsed_ms=int((time.time() - t0) * 1000),
            error="rejected: only single-statement SELECT/WITH queries are allowed",
            notes=[
                "Query must start with SELECT or WITH.",
                "Write operations and multi-statement SQL are rejected.",
            ],
        )

    bounded = _ensure_limit(raw, max_rows=max_rows)

    cfg = load_config()  # loads secrets/db.env early

    try:
        import psycopg2  # type: ignore
    except Exception as e:
        return DBQueryResult(
            ok=False,
            sql=bounded,
            columns=[],
            rows=[],
            rowcount=0,
            elapsed_ms=int((time.time() - t0) * 1000),
            error=f"psycopg2 missing: {type(e).__name__}: {e}",
        )

    # Note: connect_timeout is client-side; statement_timeout is server-side.
    try:
        conn = psycopg2.connect(
            host=cfg.db_host,
            port=cfg.db_port,
            dbname=cfg.db_name,
            user=cfg.db_user,
            password=cfg.db_password,
            connect_timeout=DEFAULT_CONNECT_TIMEOUT_SEC,
        )
    except Exception as e:
        return DBQueryResult(
            ok=False,
            sql=bounded,
            columns=[],
            rows=[],
            rowcount=0,
            elapsed_ms=int((time.time() - t0) * 1000),
            error=f"connect failed: {type(e).__name__}: {e}",
        )

    try:
        with conn:
            with conn.cursor() as cur:
                # server-side guardrails
                cur.execute("SET LOCAL statement_timeout = %s;", (int(statement_timeout_ms),))
                cur.execute("SET LOCAL idle_in_transaction_session_timeout = %s;", (int(statement_timeout_ms),))

                cur.execute(bounded, params)

                desc = cur.description or []
                cols = [d.name for d in desc]  # type: ignore[attr-defined]

                raw_rows = cur.fetchall()
                rows = [[_truncate_cell(v) for v in r] for r in raw_rows]

                elapsed_ms = int((time.time() - t0) * 1000)
                return DBQueryResult(
                    ok=True,
                    sql=bounded,
                    columns=cols,
                    rows=rows,
                    rowcount=len(rows),
                    elapsed_ms=elapsed_ms,
                    notes=[
                        f"statement_timeout_ms={int(statement_timeout_ms)}",
                        f"max_rows={int(max_rows)} (LIMIT enforced if absent)",
                    ],
                )
    except Exception as e:
        elapsed_ms = int((time.time() - t0) * 1000)
        return DBQueryResult(
            ok=False,
            sql=bounded,
            columns=[],
            rows=[],
            rowcount=0,
            elapsed_ms=elapsed_ms,
            error=f"query failed: {type(e).__name__}: {e}",
        )
    finally:
        try:
            conn.close()
        except Exception:
            pass


def tool_spec() -> dict[str, Any]:
    """
    A small “function signature” blob we can hand to the planner prompt.
    Keep it stable and versionable.
    """
    return {
        "name": "db.query",
        "description": "Execute a single-statement READ-ONLY SQL query (SELECT/WITH) against the local TAK Postgres. Results are bounded and time-limited.",
        "inputs": {
            "sql": "string (required) - must start with SELECT or WITH",
            "params": "array (optional) - positional params for %s placeholders",
            "statement_timeout_ms": "int (optional, default 3000)",
            "max_rows": "int (optional, default 200)",
        },
        "output": {
            "ok": "bool",
            "columns": "array[string]",
            "rows": "array[array]",
            "rowcount": "int",
            "elapsed_ms": "int",
            "error": "string|null",
            "notes": "array[string]|null",
        },
    }

