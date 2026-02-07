from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

import psycopg2
import psycopg2.extras


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def _parse_env_file(path: Path) -> dict[str, str]:
    """
    Parse simple KEY=VALUE env files.
    - No shell expansion
    - No quoting rules
    - Lines starting with # are ignored
    """
    out: dict[str, str] = {}
    if not path.exists():
        return out

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out


# -----------------------------------------------------------------------------
# DB config resolution
# -----------------------------------------------------------------------------

def db_config() -> dict[str, Any]:
    """
    Resolve DB config in a deterministic, installer-friendly way.

    Resolution order:
      1) Environment variables (TAKCTL_DB_*)
      2) secrets/db.env (runtime-owned, installer-preserved)
      3) PG* environment variables (last-resort fallback)

    Returns a dict compatible with psycopg2.connect(**cfg)
    """
    cfg: dict[str, Any] = {}

    env_map = {
        "TAKCTL_DB_HOST": "host",
        "TAKCTL_DB_PORT": "port",
        "TAKCTL_DB_NAME": "dbname",
        "TAKCTL_DB_USER": "user",
        "TAKCTL_DB_PASSWORD": "password",
    }

    # 1) TAKCTL_DB_* from environment
    for ek, nk in env_map.items():
        v = (os.environ.get(ek) or "").strip()
        if v:
            cfg[nk] = v

    # 2) secrets/db.env (runtime-owned)
    secrets = _parse_env_file(
        Path("/opt/tak/tools/takctl/secrets/db.env")
    )
    for ek, nk in env_map.items():
        if nk not in cfg and secrets.get(ek):
            cfg[nk] = secrets[ek]

    # 3) PG* fallback (optional)
    pg_map = {
        "PGHOST": "host",
        "PGPORT": "port",
        "PGDATABASE": "dbname",
        "PGUSER": "user",
        "PGPASSWORD": "password",
    }
    for ek, nk in pg_map.items():
        if nk not in cfg:
            v = (os.environ.get(ek) or "").strip()
            if v:
                cfg[nk] = v

    # Sensible defaults (safe for local TAK nodes)
    cfg.setdefault("host", "127.0.0.1")
    cfg.setdefault("port", 5432)
    cfg.setdefault("dbname", "cot")

    # psycopg2 quality-of-life
    cfg["connect_timeout"] = 3
    cfg["application_name"] = "takctl"

    return cfg


# -----------------------------------------------------------------------------
# DB client
# -----------------------------------------------------------------------------

class DB:
    """
    Thin psycopg2 wrapper.

    Design goals:
      - No schema assumptions
      - Dict-based rows
      - Autocommit (safe for read-heavy workloads)
      - No retries, no magic
      - One place where psycopg2 exists
    """

    def __init__(self, cfg: Optional[dict[str, Any]] = None):
        self._cfg = cfg or db_config()
        self._conn: Optional[psycopg2.extensions.connection] = None

    # ------------------------------------------------------------------

    def connect(self) -> psycopg2.extensions.connection:
        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(
                cursor_factory=psycopg2.extras.RealDictCursor,
                **self._cfg,
            )
            self._conn.autocommit = True
        return self._conn

    def close(self) -> None:
        if self._conn and not self._conn.closed:
            self._conn.close()
        self._conn = None

    # ------------------------------------------------------------------

    def query(
        self,
        sql: str,
        params: Iterable[Any] | Mapping[str, Any] | None = None,
        limit: Optional[int] = None,
    ) -> list[dict[str, Any]]:
        """
        Execute a SELECT-style query and return rows as dicts.

        NOTE:
        - Caller controls SQL text
        - This layer does NOT attempt to sanitize identifiers
        """
        conn = self.connect()
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall() or []

        if limit is not None:
            return rows[:limit]
        return rows

    def query_one(
        self,
        sql: str,
        params: Iterable[Any] | Mapping[str, Any] | None = None,
    ) -> Optional[dict[str, Any]]:
        rows = self.query(sql, params=params, limit=1)
        return rows[0] if rows else None

    def scalar(
        self,
        sql: str,
        params: Iterable[Any] | Mapping[str, Any] | None = None,
    ) -> Any:
        """
        Convenience for queries that return a single value.
        """
        row = self.query_one(sql, params=params)
        if not row:
            return None
        return next(iter(row.values()))

    # ------------------------------------------------------------------

    def __enter__(self) -> "DB":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

