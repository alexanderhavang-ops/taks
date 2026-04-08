from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

from takctl.config import load_config
from takctl.infra.db import DB

DEFAULT_CORECONFIG_XML = Path("/opt/tak/CoreConfig.xml")


def coreconfig_repo_conn(coreconfig_xml: Path = DEFAULT_CORECONFIG_XML) -> Optional[dict]:
    """
    Read TAK Server repository connection from CoreConfig.xml, if present.
    Returns: {host, port, dbname, user, password}
    """
    try:
        import xml.etree.ElementTree as ET
        from urllib.parse import urlparse

        if not coreconfig_xml.exists():
            return None

        root = ET.parse(str(coreconfig_xml)).getroot()
        ns = {"m": root.tag.split("}")[0].strip("{")} if "}" in root.tag else {}
        conn = root.find(".//m:repository/m:connection", ns) if ns else root.find(".//repository/connection")
        if conn is None:
            return None

        url = conn.attrib.get("url", "")
        user = conn.attrib.get("username", "")
        pwd = conn.attrib.get("password", "")

        if not url.startswith("jdbc:postgresql://"):
            return None

        u = urlparse(url.replace("jdbc:", "", 1))
        host = u.hostname or "127.0.0.1"
        port = int(u.port or 5432)
        dbn = (u.path or "").lstrip("/") or "cot"

        return {"host": host, "port": port, "dbname": dbn, "user": user, "password": pwd}
    except Exception:
        return None


def maybe_db() -> Tuple[Optional[DB], Optional[str], str, str]:
    """
    DB is optional for onboarding status.

    Rules (explicit, not "silent"):
      1) Start from takctl load_config() backed by runtime conf.d/secrets.d.
      2) Force db_mode=psycopg2 (web-safe).
      3) If config looks like defaults (db_user=postgres OR missing password),
         and CoreConfig.xml has a repository connection, override DB creds from CoreConfig.
      4) Probe connectivity with SELECT 1. On any failure: return (None, error, source, target).
    """
    source = "config"
    target = ""

    try:
        cfg = load_config()
        cfg.db_mode = "psycopg2"
        target = f"{cfg.db_user}@{cfg.db_host}:{cfg.db_port}/{cfg.db_name}"

        repo = coreconfig_repo_conn()
        if repo:
            looks_default_user = (getattr(cfg, "db_user", "") == "postgres")
            missing_pwd = not getattr(cfg, "db_password", None)

            if looks_default_user or missing_pwd:
                cfg.db_host = repo["host"]
                cfg.db_port = repo["port"]
                cfg.db_name = repo["dbname"]
                cfg.db_user = repo["user"] or cfg.db_user
                cfg.db_password = repo["password"] or cfg.db_password
                source = "coreconfig"
                target = f"{cfg.db_user}@{cfg.db_host}:{cfg.db_port}/{cfg.db_name}"

        db = DB(cfg)
        db.fetchall("SELECT 1", ())
        return db, None, source, target

    except Exception as e:
        return None, f"{type(e).__name__}: {e}", source, target
