from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Any


@dataclass
class DB:
    cfg: Any

    def fetchall(self, sql: str, params: tuple = ()) -> list[tuple]:
        if self.cfg.db_mode == "psycopg2":
            return self._fetchall_psycopg2(sql, params)
        if self.cfg.db_mode == "psql_sudo":
            return self._fetchall_psql_sudo(sql, params)
        raise ValueError(f"Unsupported db_mode: {self.cfg.db_mode}")

    def scalar(self, sql: str, params: tuple = ()) -> str:
        rows = self.fetchall(sql, params)
        if not rows:
            return ""
        return str(rows[0][0])

    def _fetchall_psycopg2(self, sql: str, params: tuple) -> list[tuple]:
        try:
            import psycopg2  # type: ignore
        except Exception as e:
            raise RuntimeError("psycopg2 not installed in venv") from e

        conn = psycopg2.connect(
            host=self.cfg.db_host,
            port=self.cfg.db_port,
            dbname=self.cfg.db_name,
            user=self.cfg.db_user,
            password=self.cfg.db_password,
            connect_timeout=5,
        )
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(sql, params)
                    return cur.fetchall()
        finally:
            conn.close()

    def _fetchall_psql_sudo(self, sql: str, params: tuple[Any, ...]) -> list[tuple]:
        final_sql = self._interpolate(sql, params)
        out = self._psql(final_sql).strip()
        if not out:
            return []
        rows: list[tuple] = []
        for line in out.splitlines():
            parts = line.split("\t")
            rows.append(tuple(parts))
        return rows

    def _psql(self, sql: str) -> str:
        cmd = [
            "sudo",
            "-u",
            self.cfg.sudo_user,
            "psql",
            "-d",
            self.cfg.db_name,
            "-h",
            self.cfg.db_host,
            "-p",
            str(self.cfg.db_port),
            "-At",
            "-F",
            "\t",
            "-c",
            sql,
        ]
        return subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT)

    def _interpolate(self, sql: str, params: tuple[Any, ...]) -> str:
        if not params:
            return sql
        out = sql
        for p in params:
            if p is None:
                v = "NULL"
            elif isinstance(p, (int, float)):
                v = str(p)
            else:
                s = str(p).replace("'", "''")
                v = f"'{s}'"
            out = out.replace("%s", v, 1)
        return out
