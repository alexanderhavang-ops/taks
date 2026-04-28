from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import APIRouter

from takctl.deps import get_ctx

router = APIRouter()

APPLY_JSON = Path("/opt/tak/takctl-state/apply.json")


def _read_apply_ts_utc() -> str | None:
    try:
        raw = APPLY_JSON.read_text(encoding="utf-8").strip()
        if not raw:
            return None
        data = json.loads(raw)
        v = (data.get("apply_ts_utc") if isinstance(data, dict) else None)
        return str(v) if v else None
    except Exception:
        return None


def _selected_store() -> str:
    try:
        from takctl.services.backing_user_store import selected_backing_user_store

        return selected_backing_user_store()
    except Exception:
        return "userauthfile"


@router.get("/health")
def health() -> dict:
    ctx = get_ctx()
    store = _selected_store()

    core = Path(getattr(ctx.cfg, "coreconfig_path", ""))
    out = {
        "status": "ok",
        "apply_ts_utc": _read_apply_ts_utc(),
        "backing_user_store": store,
        "coreconfig_path": str(core),
        "coreconfig_exists": core.exists(),
        "coreconfig_readable": os.access(str(core), os.R_OK) if str(core) else False,
        "auth_xml_path": None,
        "auth_xml_exists": None,
        "auth_xml_readable": None,
        "ldap": None,
        "notes": [],
    }

    # If coreconfig missing/unreadable, degrade.
    if not out["coreconfig_exists"] or not out["coreconfig_readable"]:
        out["status"] = "degraded"
        if not out["coreconfig_exists"]:
            out["notes"].append("CoreConfig.xml missing")
        if not out["coreconfig_readable"]:
            out["notes"].append("CoreConfig.xml not readable")

    if store == "ldap":
        try:
            from takctl.services.ldap_user_store import load_ldap_config

            ldap_cfg = load_ldap_config()
            out["ldap"] = {
                "uri": ldap_cfg.uri,
                "base_dn": ldap_cfg.base_dn,
                "people_base_dn": ldap_cfg.people_base_dn,
                "groups_base_dn": ldap_cfg.groups_base_dn,
                "bind_dn_configured": bool(ldap_cfg.bind_dn),
                "bind_password_configured": bool(ldap_cfg.bind_password),
                "write_dn_configured": bool(ldap_cfg.write_dn),
                "write_password_configured": bool(ldap_cfg.write_password),
            }
            if not ldap_cfg.bind_dn or not ldap_cfg.bind_password:
                out["status"] = "degraded"
                out["notes"].append("LDAP bind DN/password not configured")
        except Exception as e:
            out["status"] = "degraded"
            out["notes"].append(f"LDAP config error: {e}")
        return out

    # userauthfile mode: resolve auth xml via CoreConfig.xml.
    try:
        from takctl.services.userauth_file import auth_file_path

        p = auth_file_path(str(core))
        out["auth_xml_path"] = p
        out["auth_xml_exists"] = Path(p).exists()
        out["auth_xml_readable"] = os.access(p, os.R_OK)
    except Exception as e:
        out["status"] = "degraded"
        out["notes"].append(str(e))

    return out
