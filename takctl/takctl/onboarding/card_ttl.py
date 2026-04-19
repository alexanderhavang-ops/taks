from __future__ import annotations

from fastapi import HTTPException
from takctl.config import load_config


def required_card_link_ttl_sec() -> int:
    raw = str(load_config().get("onboarding_card_token_ttl_sec", "") or "").strip()
    if not raw:
        raise HTTPException(status_code=500, detail="missing required config: onboarding_card_token_ttl_sec")
    try:
        ttl = int(raw)
    except Exception:
        raise HTTPException(status_code=500, detail=f"invalid onboarding_card_token_ttl_sec: {raw!r}")
    if ttl < 1:
        raise HTTPException(status_code=500, detail=f"invalid onboarding_card_token_ttl_sec: {raw!r}")
    return ttl
