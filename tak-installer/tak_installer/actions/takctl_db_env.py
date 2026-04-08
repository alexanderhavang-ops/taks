from __future__ import annotations

import secrets
import subprocess
from pathlib import Path

from tak_installer.util import log


CONF_D = Path("/opt/tak/tools/takctl/conf.d")
SECRETS_D = Path("/opt/tak/tools/takctl/secrets.d")
CONF_DB = CONF_D / "db.conf"
SECRETS_DB = SECRETS_D / "db.conf"

LEGACY_SECRETS_DIR = Path("/opt/tak/tools/takctl/secrets")
LEGACY_DB_ENV = LEGACY_SECRETS_DIR / "db.env"


def _parse_kv_text(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in str(text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip()
        if k:
            out[k] = v
    return out


def _parse_env_text(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in str(text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip()
        if k:
            out[k] = v
    return out


def _read_kv(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    return _parse_kv_text(path.read_text(encoding="utf-8"))


def _read_env(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    return _parse_env_text(path.read_text(encoding="utf-8"))


def _write_kv(path: Path, data: dict[str, str], mode: int = 0o640) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    rows = [f"{k} = {data[k]}" for k in sorted(data.keys())]
    tmp.write_text("\n".join(rows) + "\n", encoding="utf-8")
    tmp.chmod(mode)
    tmp.replace(path)


def _require(path: Path, key: str, data: dict[str, str]) -> str:
    val = str(data.get(key) or "").strip()
    if not val:
        raise RuntimeError(f"takctl-db-env: missing required key {key!r} in {path}")
    return val


def _ensure_db_secret() -> dict[str, str]:
    if not CONF_D.is_dir():
        raise RuntimeError(f"takctl-db-env: missing runtime conf.d: {CONF_D}")
    if not SECRETS_D.is_dir():
        raise RuntimeError(f"takctl-db-env: missing runtime secrets.d: {SECRETS_D}")
    if not CONF_DB.is_file():
        raise RuntimeError(f"takctl-db-env: missing runtime DB config: {CONF_DB}")

    cur = _read_kv(SECRETS_DB)
    if not (cur.get("db_password") or "").strip():
        legacy = _read_env(LEGACY_DB_ENV)
        db_pw = str(legacy.get("TAKCTL_DB_PASSWORD") or "").strip()
        if not db_pw:
            db_pw = secrets.token_urlsafe(24)
        cur["db_password"] = db_pw
        _write_kv(SECRETS_DB, cur, 0o640)
        subprocess.run(["chown", "tak:tak", str(SECRETS_DB)], check=False)
        log.info("takctl-db-env: ensured %s", SECRETS_DB)

    if LEGACY_DB_ENV.exists():
        LEGACY_DB_ENV.unlink()
        try:
            if LEGACY_SECRETS_DIR.is_dir() and not any(LEGACY_SECRETS_DIR.iterdir()):
                LEGACY_SECRETS_DIR.rmdir()
        except Exception:
            pass

    return cur


def _load_db_runtime() -> dict[str, str]:
    conf = _read_kv(CONF_DB)
    sec = _ensure_db_secret()

    cfg = {
        "db_host": _require(CONF_DB, "db_host", conf),
        "db_port": _require(CONF_DB, "db_port", conf),
        "db_name": _require(CONF_DB, "db_name", conf),
        "db_user": _require(CONF_DB, "db_user", conf),
        "db_password": _require(SECRETS_DB, "db_password", sec),
    }
    return cfg


def _sync_postgres_role(cfg: dict[str, str]) -> None:
    host = cfg["db_host"]
    port = cfg["db_port"]
    db = cfg["db_name"]
    user = cfg["db_user"]
    pw = cfg["db_password"]

    if host not in ("127.0.0.1", "localhost"):
        log.info("takctl-db-env: postgres sync skipped (non-local host=%s)", host)
        return

    if subprocess.run(["bash", "-lc", "command -v psql >/dev/null 2>&1"]).returncode != 0:
        log.info("takctl-db-env: postgres sync skipped (psql not installed)")
        return

    sql = f"""
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{user}') THEN
    CREATE ROLE {user} LOGIN;
  END IF;
END
$$;

ALTER ROLE {user} WITH LOGIN PASSWORD '{pw}';

GRANT CONNECT ON DATABASE {db} TO {user};

\\connect {db}

GRANT USAGE ON SCHEMA public TO {user};
GRANT SELECT ON ALL TABLES IN SCHEMA public TO {user};

ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO {user};
"""

    p = subprocess.run(
        ["sudo", "-u", "postgres", "psql", "-v", "ON_ERROR_STOP=1", "-q"],
        input=sql,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if p.returncode != 0:
        log.info("takctl-db-env: postgres sync failed (rc=%s):\n%s", p.returncode, (p.stdout or "").strip())
        return

    log.info("takctl-db-env: postgres role synced for %s on db=%s host=%s port=%s", user, db, host, port)


def _verify_login(cfg: dict[str, str]) -> None:
    host = cfg["db_host"]
    port = cfg["db_port"]
    db = cfg["db_name"]
    user = cfg["db_user"]
    pw = cfg["db_password"]

    cmd = (
        f'PGPASSWORD="{pw}" psql -h "{host}" -p "{port}" -U "{user}" -d "{db}" '
        f'-v ON_ERROR_STOP=1 -qtA -c "select 1;"'
    )
    p = subprocess.run(
        ["sudo", "-u", "tak", "bash", "-lc", cmd],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if p.returncode == 0:
        log.info("takctl-db-env: verified DB login for %s", user)
    else:
        log.info("takctl-db-env: DB login verification failed (rc=%s):\n%s", p.returncode, (p.stdout or "").strip())


def apply(ctx) -> None:
    cfg = _load_db_runtime()
    _sync_postgres_role(cfg)
    _verify_login(cfg)


class _Action:
    ID = "takctl-db-env"

    def inspect(self, ctx) -> int:
        log.info("Inspecting %s action...", self.ID)
        log.info("  runtime conf db: %s", CONF_DB)
        log.info("  runtime secrets db: %s", SECRETS_DB)
        log.info("  legacy db env: %s", LEGACY_DB_ENV)
        return 0

    def apply(self, ctx) -> int:
        log.info("Applying %s action...", self.ID)
        apply(ctx)
        return 0


ACTION = _Action()
