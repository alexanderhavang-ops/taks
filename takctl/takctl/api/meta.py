from __future__ import annotations

import json
import socket
from pathlib import Path

from fastapi import APIRouter

from takctl import __version__
from takctl.config import load_config

router = APIRouter()

# Runtime-owned brand asset (orchestrator/uploader writes here)
BRAND_JSON = Path("/opt/tak/tools/takctl/assets/brand.json")


def _load_brand() -> dict:
    """
    Best-effort load of runtime brand metadata.
    Must never hard-fail the /api/meta endpoint.
    """
    try:
        if not BRAND_JSON.exists():
            return {}
        data = json.loads(BRAND_JSON.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


@router.get("/meta")
def meta():
    cfg = load_config()

    # Stable node label for both web + CLI:
    # battalion (logical) -> fqdn -> hostname -> OS hostname
    node = (
        getattr(cfg, "battalion", None)
        or getattr(cfg, "fqdn", None)
        or getattr(cfg, "hostname", None)
        or socket.gethostname()
    )

    brand = _load_brand()

    # Keep existing stable keys, only add new ones.
    return {
        "product": "taks",
        "version": __version__,
        "node": node,
        "brand": brand,
        # Convenience aliases (UI accepts multiple shapes):
        "slogan": brand.get("slogan", "") if isinstance(brand, dict) else "",
        "title": brand.get("title", "") if isinstance(brand, dict) else "",
    }

