from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Optional

from takctl.config import load_config, load_secrets


@dataclass
class QueryResult:
    ok: bool
    rowcount: Optional[int] = None
    elapsed_ms: Optional[int] = None
    columns: Optional[list[str]] = None
    rows: Optional[list[list[Any]]] = None
    error: Optional[str] = None


def _conn_params() -> dict[str, Any]:
    cfg = load_config()
    sec = load_secrets()

    return {
        "host": cfg.db_host,
        "port": int(cfg.db_port),
        "dbname": cfg.db_name,
        "user": cfg.db_user,
        "password": sec.db_password or None,
    }


def run_sql(sql_text: str, *, max_rows: int = 2000) -> QueryResult:
    t0 = time.time()
    try:
        import psycopg2  # type: ignore

        params = _conn_params()
        with psycopg2.connect(**params) as conn:
            with conn.cursor() as cur:
                cur.execute(sql_text)
                cols = None
                rows = None
                rc = None
                try:
                    if cur.description:
                        cols = [d.name for d in cur.description]
                        rows = cur.fetchmany(max_rows)
                        rows = [list(r) for r in rows]
                    rc = cur.rowcount
                except Exception:
                    pass

        dt = int((time.time() - t0) * 1000)
        return QueryResult(ok=True, rowcount=rc, elapsed_ms=dt, columns=cols, rows=rows)
    except Exception as e:
        dt = int((time.time() - t0) * 1000)
        return QueryResult(ok=False, elapsed_ms=dt, error=f"{type(e).__name__}: {e}")
