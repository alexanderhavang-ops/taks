from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from takctl.config import Config
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


def _maybe_db() -> Tuple[Optional[DB], Optional[str]]:
    """
    DB is optional for onboarding status.
    Only attach if we can actually connect (otherwise return None + error).

    If takctl isn't configured with DB credentials (common under systemd),
    fall back to the TAK Server CoreConfig.xml repository connection which
    already contains the Postgres URL + username + password.
    """
    def _fill_from_coreconfig(cfg: Config) -> None:
        try:
            import xml.etree.ElementTree as ET
            from urllib.parse import urlparse

            core = Path("/opt/tak/CoreConfig.xml")
            if not core.exists():
                return

            root = ET.parse(str(core)).getroot()

            # CoreConfig.xml uses a default namespace
            ns = {"m": root.tag.split("}")[0].strip("{")} if "}" in root.tag else {}
            conn = root.find(".//m:repository/m:connection", ns) if ns else root.find(".//repository/connection")
            if conn is None:
                return

            url = conn.attrib.get("url", "")
            user = conn.attrib.get("username", "")
            pwd  = conn.attrib.get("password", "")

            if url.startswith("jdbc:postgresql://"):
                u = urlparse(url.replace("jdbc:", "", 1))
                host = u.hostname or "127.0.0.1"
                port = int(u.port or 5432)
                dbn  = (u.path or "").lstrip("/") or "cot"
            else:
                return

            # Only fill what is missing
            if not getattr(cfg, "db_host", None):
                cfg.db_host = host
            if not getattr(cfg, "db_port", None):
                cfg.db_port = port
            if not getattr(cfg, "db_name", None):
                cfg.db_name = dbn
            if not getattr(cfg, "db_user", None):
                cfg.db_user = user or getattr(cfg, "db_user", None)
            if not getattr(cfg, "db_password", None):
                cfg.db_password = pwd or getattr(cfg, "db_password", None)
        except Exception:
            # If this fallback fails, we still just run in "no DB" mode
            return

    try:
        cfg = Config()
        cfg.db_mode = "psycopg2"

        # If systemd/env didn't provide a password, fill from CoreConfig.xml
        if not getattr(cfg, "db_password", None):
            _fill_from_coreconfig(cfg)

        db = DB(cfg)

        # prove we can connect (prevents 500s if password/env is missing under systemd)
        db.fetchall("SELECT 1", ())
        return db, None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"
@router.get("/onboarding/status")
def onboarding_status(
    unknown_limit: int = Query(50, ge=0, le=500),
    recent_minutes: int = Query(120, ge=1, le=24 * 60),
):
    svc = _build_service()
    db, db_err = _maybe_db()

    out = svc.status(
        db=db,
        unknown_limit=int(unknown_limit),
        recent_minutes=int(recent_minutes),
    )

    out.setdefault("meta", {})
    out["meta"]["db_attached"] = db is not None
    if db is None and db_err:
        out["meta"]["db_error"] = db_err
    return JSONResponse(out)
