from __future__ import annotations

import os
import socket
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
    Parse a simple conf file.

    Supported formats:
      - INI-ish (your current takctl.conf):
          [takctl]
          key = value
      - Simple KV:
          KEY=VALUE

    Notes:
      - Ignores section headers like [takctl]
      - Ignores comments starting with #
      - Stores keys as written (case-sensitive), but takctl looks up lowercase names
    """
    p = Path(path)
    if not p.exists():
        return {}

    out: dict[str, str] = {}
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            continue
        if "=" not in line:
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

    # Identity (optional; used by /api/v1/meta and UI)
    battalion: str = ""
    fqdn: str = ""
    hostname: str = ""

    # Paths
    coreconfig_path: str = "/opt/tak/CoreConfig.xml"
    ca_dir: str = "/opt/tak/certs/files/00_CA"
    crl_path: str = "/opt/tak/certs/files/ca.crl"

    # CRL signing helper + CA signing keystore
    crl_sign_helper: str = "/usr/local/sbin/takctl-crl-sign"
    crl_sign_helper_timeout_sec: int = 60

    ca_signing_p12: str = "/opt/tak/certs/files/00_CA/ca-signing.p12"
    ca_signing_p12_pass: Optional[str] = None
    ca_signing_alias: str = "tak-ca"

    # How long CRLs should be valid (days)
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

    def validate(self) -> None:
        # db_mode sanity
        if self.db_mode not in ("psql_sudo", "psycopg2"):
            raise ValueError(f"Invalid db_mode={self.db_mode!r} (expected 'psql_sudo' or 'psycopg2')")

        # Guardrail: psycopg2 mode is used by the WebUI/backend and needs credentials.
        # If this trips, you're likely accidentally constructing Config() defaults
        # instead of calling load_config() (which loads secrets/db.env + takctl.conf).
        if self.db_mode == "psycopg2" and not self.db_password:
            raise ValueError("psycopg2 requires db_password (use load_config(); ensure secrets/db.env or takctl.conf provides it)")

        # required paths
        for label, p in (
            ("coreconfig_path", self.coreconfig_path),
            ("ca_dir", self.ca_dir),
            ("ca_signing_p12", self.ca_signing_p12),
            ("crl_sign_helper", self.crl_sign_helper),
        ):
            if not p:
                raise ValueError(f"{label} is empty")
            if not Path(p).exists():
                raise FileNotFoundError(f"{label} does not exist: {p}")

        # crl_path may not exist yet (first run), but parent dir should
        crl_parent = Path(self.crl_path).parent
        if not crl_parent.exists():
            raise FileNotFoundError(f"crl_path parent directory does not exist: {crl_parent}")


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
    conf_path = path or os.environ.get("TAKCTL_CONFIG") or DEFAULT_CONFIG_PATH
    file_kv = _parse_conf_kv(conf_path)

    # Normalize file keys: your file uses lowercase keys, keep that working
    # while still letting KEY=VALUE work.
    file_kv_norm: dict[str, str] = {}
    for k, v in file_kv.items():
        file_kv_norm[k.strip()] = v.strip()

    def get(name: str, default: str) -> str:
        """
        Read from env (TAKCTL_NAME), else file (name), else default.
        Treat empty string as "not set".
        """
        env_key = f"TAKCTL_{name.upper()}"
        if env_key in os.environ and os.environ[env_key] != "":
            return os.environ[env_key]
        if name in file_kv_norm and file_kv_norm[name] != "":
            return file_kv_norm[name]
        return default

    cfg = Config(
        battalion=get("battalion", ""),
        fqdn=get("fqdn", ""),
        hostname=get("hostname", socket.gethostname()),

        db_mode=get("db_mode", Config.db_mode),
        db_name=get("db_name", Config.db_name),
        db_host=get("db_host", Config.db_host),
        db_port=int(get("db_port", str(Config.db_port))),
        db_user=get("db_user", Config.db_user),
        db_password=os.environ.get("TAKCTL_DB_PASSWORD") or file_kv_norm.get("db_password") or None,
        sudo_user=get("sudo_user", Config.sudo_user),

        coreconfig_path=get("coreconfig_path", Config.coreconfig_path),
        ca_dir=get("ca_dir", Config.ca_dir),
        crl_path=get("crl_path", Config.crl_path),

        crl_sign_helper=get("crl_sign_helper", Config.crl_sign_helper),
        crl_sign_helper_timeout_sec=int(get("crl_sign_helper_timeout_sec", str(Config.crl_sign_helper_timeout_sec))),

        ca_signing_p12=get("ca_signing_p12", Config.ca_signing_p12),
        ca_signing_p12_pass=os.environ.get("TAKCTL_CA_SIGNING_P12_PASS") or file_kv_norm.get("ca_signing_p12_pass") or None,
        ca_signing_alias=get("ca_signing_alias", Config.ca_signing_alias),

        crl_days=int(get("crl_days", str(Config.crl_days))),
        tak_service=get("tak_service", Config.tak_service),

        llm_enabled=(get("llm_enabled", "true").lower() in ("1", "true", "yes", "y", "on")),
        llm_url=get("llm_url", Config.llm_url),
        llm_unit=get("llm_unit", Config.llm_unit),

        audit_log=get("audit_log", Config.audit_log),

        _loaded_from=conf_path if Path(conf_path).exists() else None,
    )

    return cfg
