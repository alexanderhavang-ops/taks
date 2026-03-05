from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

DEFAULT_DB_ENV = Path("/opt/tak/tools/takctl/secrets/db.env")


@dataclass
class QueryResult:
    ok: bool
    rowcount: Optional[int] = None
    elapsed_ms: Optional[int] = None
    columns: Optional[list[str]] = None
    rows: Optional[list[list[Any]]] = None
    error: Optional[str] = None


def _parse_env_file(path: Path) -> Dict[str, str]:
    """
    Minimal .env parser:
      - supports KEY=VALUE
      - ignores blank lines and lines starting with '#'
      - strips surrounding quotes on VALUE
    """
    out: Dict[str, str] = {}
    try:
        txt = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return out

    for raw in txt.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip()

        if len(v) >= 2 and ((v[0] == v[-1] == '"') or (v[0] == v[-1] == "'")):
            v = v[1:-1]

        if k:
            out[k] = v
    return out


def _ensure_db_env_loaded(env_path: Path = DEFAULT_DB_ENV) -> None:
    """
    If TAKCTL_DB_PASSWORD is missing from process env, try to load TAKCTL_DB_*
    keys from installer-owned db.env. Does NOT override already-set env vars.
    """
    if (os.environ.get("TAKCTL_DB_PASSWORD") or "").strip():
        return
    if not env_path.exists():
        return

    vals = _parse_env_file(env_path)
    for k, v in vals.items():
        if not k.startswith("TAKCTL_DB_"):
            continue
        if (os.environ.get(k) or "").strip():
            continue
        os.environ[k] = v


def _conn_params_from_env(*, env_path: Path = DEFAULT_DB_ENV) -> dict[str, Any]:
    # matches db.env created by installer action takctl-db-env
    _ensure_db_env_loaded(env_path)

    host = (os.environ.get("TAKCTL_DB_HOST") or "127.0.0.1").strip()
    port = int((os.environ.get("TAKCTL_DB_PORT") or "5432").strip())
    dbname = (os.environ.get("TAKCTL_DB_NAME") or "cot").strip()
    user = (os.environ.get("TAKCTL_DB_USER") or "takctl_ro").strip()
    password = (os.environ.get("TAKCTL_DB_PASSWORD") or "").strip() or None

    return {"host": host, "port": port, "dbname": dbname, "user": user, "password": password}


def run_sql(sql_text: str, *, max_rows: int = 2000, env_path: Path = DEFAULT_DB_ENV) -> QueryResult:
    """
    Execute SQL and return QueryResult.
    Uses env vars, but will auto-load /opt/tak/tools/takctl/secrets/db.env
    if TAKCTL_DB_PASSWORD is missing in the current process environment.
    """
    t0 = time.time()
    try:
        import psycopg2  # type: ignore

        params = _conn_params_from_env(env_path=env_path)
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
