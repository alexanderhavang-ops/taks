from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Optional

import psycopg2


@dataclass
class QueryResult:
    ok: bool
    rowcount: Optional[int] = None
    elapsed_ms: Optional[int] = None
    columns: Optional[list[str]] = None
    rows: Optional[list[list[Any]]] = None
    error: Optional[str] = None


def _conn_params_from_env() -> dict[str, Any]:
    # matches db.env created by installer action takctl-db-env
    host = (os.environ.get("TAKCTL_DB_HOST") or "127.0.0.1").strip()
    port = int((os.environ.get("TAKCTL_DB_PORT") or "5432").strip())
    dbname = (os.environ.get("TAKCTL_DB_NAME") or "cot").strip()
    user = (os.environ.get("TAKCTL_DB_USER") or "takctl_ro").strip()
    password = (os.environ.get("TAKCTL_DB_PASSWORD") or "").strip() or None
    return {"host": host, "port": port, "dbname": dbname, "user": user, "password": password}


def run_sql(sql_text: str, *, max_rows: int = 2000) -> QueryResult:
    t0 = time.time()
    try:
        params = _conn_params_from_env()
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
