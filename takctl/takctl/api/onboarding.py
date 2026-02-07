from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from takctl.config import load_config
from takctl.infra.db import DB
from takctl.onboarding.service import OnboardingService
from takctl.onboarding.store_filejson import FileJsonOnboardingStore
from takctl.onboarding.user_directory_xml import UserDirectoryXml

router = APIRouter(tags=["onboarding"])

DEFAULT_USERAUTH_XML = Path("/opt/tak/UserAuthenticationFile.xml")
DEFAULT_STATE_ROOT = Path("/opt/tak/takctl-state/onboarding")


def _build_service(
    userauth_xml: Path = DEFAULT_USERAUTH_XML,
    state_root: Path = DEFAULT_STATE_ROOT,
) -> OnboardingService:
    ud = UserDirectoryXml(str(userauth_xml))
    store = FileJsonOnboardingStore(str(state_root))
    return OnboardingService(ud=ud, store=store)


def _coreconfig_repo_conn() -> Optional[dict]:
    """
    Read TAK Server repository connection from CoreConfig.xml, if present.
    Returns: {host, port, dbname, user, password}
    """
    try:
        import xml.etree.ElementTree as ET
        from urllib.parse import urlparse

        core = Path("/opt/tak/CoreConfig.xml")
        if not core.exists():
            return None

        root = ET.parse(str(core)).getroot()
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


def _maybe_db() -> Tuple[Optional[DB], Optional[str], str, str]:
    """
    DB is optional for onboarding status.

    Rules (explicit, not "silent"):
      1) Start from takctl load_config() (env + takctl.conf + defaults).
         NOTE: load_config() also loads secrets/db.env into env first.
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

        repo = _coreconfig_repo_conn()
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


@router.get("/onboarding/status")
def onboarding_status(
    unknown_limit: int = Query(50, ge=0, le=500),
    recent_minutes: int = Query(120, ge=1, le=24 * 60),
):
    svc = _build_service()
    db, db_err, db_source, db_target = _maybe_db()

    out = svc.status(
        db=db,
        unknown_limit=int(unknown_limit),
        recent_minutes=int(recent_minutes),
    )

    out.setdefault("meta", {})
    out["meta"]["db_attached"] = db is not None
    out["meta"]["db_source"] = db_source
    out["meta"]["db_target"] = db_target
    if db is None and db_err:
        out["meta"]["db_error"] = db_err

    return JSONResponse(out)
