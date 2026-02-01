from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


DEFAULT_CONFIG_PATH = "/opt/tak/tools/takctl/takctl.conf"
DEFAULT_DB_ENV_PATH = "/opt/tak/tools/takctl/secrets/db.env"


def _load_envfile(path: str) -> None:
    """
    Minimal .env reader: KEY=VALUE per line.
    Does not overwrite existing environment variables.
    Silently ignores missing file.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip()
                if k and k not in os.environ:
                    os.environ[k] = v
    except FileNotFoundError:
        return


def _parse_conf_kv(path: str) -> dict[str, str]:
    """
    Parse a simple conf file:
      KEY=VALUE
      # comments allowed
    """
    p = Path(path)
    if not p.exists():
        return {}
    out: dict[str, str] = {}
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out


@dataclass
class Config:
    # DB
    db_mode: str = "psql_sudo"  # legacy default; can be overridden to psycopg2
    db_name: str = "cot"
    db_host: str = "127.0.0.1"
    db_port: int = 5432
    db_user: str = "postgres"
    db_password: Optional[str] = None
    sudo_user: str = "postgres"

    # Paths
    coreconfig_path: str = "/opt/tak/CoreConfig.xml"
    ca_dir: str = "/opt/tak/certs/files/00_CA"
    crl_path: str = "/opt/tak/certs/files/ca.crl"
    ca_signing_p12: str = "/opt/tak/certs/files/00_CA/ca-signing.p12"
    ca_signing_p12_pass: Optional[str] = None
    ca_signing_alias: str = "tak-ca"
    crl_days: int = 30
    tak_service: str = "takserver"

    # LLM (optional)
    llm_enabled: bool = True
    llm_url: str = "http://127.0.0.1:8090"
    llm_unit: str = "llm-local"

    # Logging
    audit_log: str = "/opt/tak/tools/takctl/takctl.audit.log"

    # Internal: where config was loaded from (debugging)
    _loaded_from: Optional[str] = None


def load_config(path: Optional[str] = None) -> Config:
    """
    Load configuration for takctl.

    Precedence (highest wins):
      1) Environment variables (TAKCTL_*)
      2) File config (path parameter OR $TAKCTL_CONFIG OR DEFAULT_CONFIG_PATH)
      3) Defaults in Config dataclass

    Also loads DEFAULT_DB_ENV_PATH early (if present) to populate DB env vars
    for non-interactive use (WebUI/backend-friendly).
    """
    # 0) Load db.env early (does not override existing env)
    _load_envfile(DEFAULT_DB_ENV_PATH)

    # 1) Decide which conf file to read (if any)
    conf_path = (
        path
        or os.environ.get("TAKCTL_CONFIG")
        or DEFAULT_CONFIG_PATH
    )
    file_kv = _parse_conf_kv(conf_path)

    # Helper to read from env, else file, else default
    def get(name: str, default: str) -> str:
        env_key = f"TAKCTL_{name.upper()}"
        if env_key in os.environ and os.environ[env_key] != "":
            return os.environ[env_key]
        if name in file_kv and file_kv[name] != "":
            return file_kv[name]
        return default

    cfg = Config(
        db_mode=get("db_mode", Config.db_mode),
        db_name=get("db_name", Config.db_name),
        db_host=get("db_host", Config.db_host),
        db_port=int(get("db_port", str(Config.db_port))),
        db_user=get("db_user", Config.db_user),
        db_password=os.environ.get("TAKCTL_DB_PASSWORD") or file_kv.get("db_password") or None,
        sudo_user=get("sudo_user", Config.sudo_user),

        coreconfig_path=get("coreconfig_path", Config.coreconfig_path),
        ca_dir=get("ca_dir", Config.ca_dir),
        crl_path=get("crl_path", Config.crl_path),
        ca_signing_p12=get("ca_signing_p12", Config.ca_signing_p12),
        ca_signing_p12_pass=os.environ.get("TAKCTL_CA_SIGNING_P12_PASS") or file_kv.get("ca_signing_p12_pass") or None,
        ca_signing_alias=get("ca_signing_alias", Config.ca_signing_alias),
        crl_days=int(get("crl_days", str(Config.crl_days))),
        tak_service=get("tak_service", Config.tak_service),

        llm_enabled=(get("llm_enabled", "true").lower() in ("1","true","yes","y","on")),
        llm_url=get("llm_url", Config.llm_url),
        llm_unit=get("llm_unit", Config.llm_unit),

        audit_log=get("audit_log", Config.audit_log),
        _loaded_from=conf_path if Path(conf_path).exists() else None,
    )

    return cfg

