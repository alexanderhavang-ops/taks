from __future__ import annotations

from typing import Dict, Any

from fastapi import APIRouter, Request

from .api_v2 import require_operator
from orchestrator_core.config import (
    apply_config_updates,
    config_public_state,
)

router = APIRouter(prefix="/api/v2/settings", tags=["settings"])


@router.get("")
def get_settings_info(request: Request) -> Dict[str, Any]:
    require_operator(request)
    st = config_public_state()
    return {
        "ok": True,
        "config_root": st.get("config_root"),
        "secrets_root": st.get("secrets_root"),
        "config_exists": st.get("config_exists"),
        "secrets_exists": st.get("secrets_exists"),
        "config_path": st.get("config_path"),
        "secrets_path": st.get("secrets_path"),
        "components": st.get("components", []),
        "values": st.get("values", {}),
        "secret_keys": st.get("secret_keys", []),
        "has_secrets": st.get("has_secrets", {}),
    }


@router.post("")
async def post_settings_info(request: Request) -> Dict[str, Any]:
    require_operator(request)
    body = await request.json()
    if not isinstance(body, dict):
        body = {}

    cfg, sec = apply_config_updates(
        config_updates=(body.get("config_updates") or {}),
        secret_updates=(body.get("secret_updates") or {}),
    )
    st = config_public_state()
    return {
        "ok": True,
        "saved_config_keys": sorted(list((body.get("config_updates") or {}).keys())),
        "saved_secret_keys": sorted(list((body.get("secret_updates") or {}).keys())),
        "config_root": st.get("config_root"),
        "secrets_root": st.get("secrets_root"),
        "components": st.get("components", []),
        "values": st.get("values", {}),
        "secret_keys": st.get("secret_keys", []),
        "has_secrets": st.get("has_secrets", {}),
    }
