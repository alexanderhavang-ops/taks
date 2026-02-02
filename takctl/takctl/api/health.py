from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter

from takctl.deps import get_ctx

router = APIRouter()


@router.get("/health")
def health() -> dict:
    ctx = get_ctx()

    core = Path(getattr(ctx.cfg, "coreconfig_path", ""))
    out = {
        "status": "ok",
        "coreconfig_path": str(core),
        "coreconfig_exists": core.exists(),
        "coreconfig_readable": os.access(str(core), os.R_OK) if str(core) else False,
        "auth_xml_path": None,
        "auth_xml_exists": None,
        "auth_xml_readable": None,
        "notes": [],
    }

    # Resolve auth xml via CoreConfig.xml (best-effort; don't crash health)
    try:
        from takctl.services.userauth_file import auth_file_path

        p = auth_file_path(str(core))
        out["auth_xml_path"] = p
        out["auth_xml_exists"] = Path(p).exists()
        out["auth_xml_readable"] = os.access(p, os.R_OK)
    except Exception as e:
        out["status"] = "degraded"
        out["notes"].append(str(e))

    # If coreconfig missing/unreadable, degrade
    if not out["coreconfig_exists"] or not out["coreconfig_readable"]:
        out["status"] = "degraded"
        if not out["coreconfig_exists"]:
            out["notes"].append("CoreConfig.xml missing")
        if not out["coreconfig_readable"]:
            out["notes"].append("CoreConfig.xml not readable")

    return out
