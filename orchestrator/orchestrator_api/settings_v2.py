from __future__ import annotations

from pathlib import Path
from typing import Dict

from fastapi import APIRouter, Request

from .api_v2 import require_operator

router = APIRouter(prefix="/api/v2/settings", tags=["settings"])

CONFIG_PATH = Path("/etc/taks/tak_orch.conf")
SECRETS_PATH = Path("/etc/taks/secrets.conf")


@router.get("")
def get_settings_info(request: Request) -> Dict[str, object]:
    require_operator(request)
    return {
        "ok": True,
        "config_path": str(CONFIG_PATH),
        "secrets_path": str(SECRETS_PATH),
        "config_exists": CONFIG_PATH.exists(),
        "secrets_exists": SECRETS_PATH.exists(),
    }
