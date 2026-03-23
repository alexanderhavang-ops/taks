from __future__ import annotations

from typing import Any, Iterable, Mapping, Optional

import psycopg2
import psycopg2.extras

from takctl.config import load_config, load_secrets


def db_config() -> dict[str, Any]:
    cfg = load_config()
    sec = load_secrets()

    return {
        "host": cfg.db_host,
        "port": int(cfg.db_port),
        "dbname": cfg.db_name,
        "user": cfg.db_user,
        "password": sec.db_password or None,
        "connect_timeout": 3,
        "application_name": "takctl",
    }


class DB:
    """
    Thin psycopg2 wrapper.
    """

    def __init__(self, cfg: Optional[dict[str, Any]] = None):
        self._cfg = cfg or db_config()
        self._conn: Optional[psycopg2.extensions.connection] = None

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

    def query(
        self,
        sql: str,
        params: Iterable[Any] | Mapping[str, Any] | None = None,
        limit: Optional[int] = None,
    ) -> list[dict[str, Any]]:
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
        row = self.query_one(sql, params=params)
        if not row:
            return None
        return next(iter(row.values()))

    def __enter__(self) -> "DB":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
