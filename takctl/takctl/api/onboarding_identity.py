from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from takctl.onboarding.onboarding_db import maybe_db
from takctl.onboarding.service_builder import build_service
router = APIRouter(tags=["onboarding"])


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class IdentityUpsertIn(BaseModel):
    origin: str = Field(default="marti", description='taks|marti')
    password: Optional[str] = Field(default=None, description="Only stored when origin=taks")
    ctx: Dict[str, Any] = Field(default_factory=dict)


class CardTokenCreateIn(BaseModel):
    ttl_sec: int = Field(default=3600, ge=60, le=7 * 24 * 3600)
    reveal_password: bool = Field(default=False)


@router.post("/onboarding/users/{username}/identity")
def upsert_identity(username: str, body: IdentityUpsertIn):
    username = (username or "").strip()
    if not username:
        raise HTTPException(status_code=400, detail="username required")

    origin = (body.origin or "marti").strip().lower()
    if origin not in ("taks", "marti"):
        raise HTTPException(status_code=400, detail="origin must be 'taks' or 'marti'")

    svc = build_service()

    # only allow identities for users that exist in authoritative directory
    u = svc.ud.get_user(username)
    if u is None:
        raise HTTPException(status_code=404, detail=f"user not found in UserAuthenticationFile.xml: {username}")

    # Store API requires: username, origin, ctx, identity, password

    ident = svc.store.upsert_identity(

        username=username,

        origin=origin,

        ctx=(body.ctx or {}),

        identity={},  # reserved for future (callsign/team/atak_role_type etc)

        password=(body.password or None),

    )
    return JSONResponse(
        {
            "identity": {
                "username": ident.username,
                "origin": ident.origin,
                "password_known": bool(ident.password_known),
                "ctx": ident.ctx or {},
            }
        },
        headers={"cache-control": "no-store, max-age=0", "pragma": "no-cache"},
    )


@router.post("/onboarding/users/{username}/card-token")
def create_card_token(username: str, body: CardTokenCreateIn):
    username = (username or "").strip()
    if not username:
        raise HTTPException(status_code=400, detail="username required")

    svc = build_service()

    # only allow tokens for users that exist in authoritative directory
    u = svc.ud.get_user(username)
    if u is None:
        raise HTTPException(status_code=404, detail=f"user not found in UserAuthenticationFile.xml: {username}")

    # Store API drift guard:

    # - new: create_card_token(username=..., ttl_sec=..., reveal_password=...)

    # - old: upsert_card_token(username=..., ttl_sec=..., reveal_password=...)

    if hasattr(svc.store, "create_card_token"):

        ct = svc.store.create_card_token(

            username=username,

            ttl_sec=int(body.ttl_sec),

            reveal_password=bool(body.reveal_password),

        )

    elif hasattr(svc.store, "upsert_card_token"):

        ct = svc.store.upsert_card_token(

            username=username,

            ttl_sec=int(body.ttl_sec),

            reveal_password=bool(body.reveal_password),

        )

    else:

        raise HTTPException(status_code=500, detail="Onboarding store missing card-token creator (create_card_token/upsert_card_token)")

    # URL surface is a UI decision; return token + expiry for now.
    return JSONResponse(
        {
            "card_token": {
                "token": ct.token,
                "username": ct.username,
                "expires_at": ct.expires_at_utc.isoformat().replace("+00:00", "Z"),
                "reveal_password": bool(ct.reveal_password),
            }
        },
        headers={"cache-control": "no-store, max-age=0", "pragma": "no-cache"},
    )
@router.get("/onboarding/cards/{token}.json")
def onboarding_card_by_token_json(
    token: str,
    recent_minutes: int = Query(120, ge=1, le=24 * 60),
):
    """
    Token-resolved card JSON:
      - resolves CardToken -> username (authoritative user must exist)
      - enforces TTL
      - optionally reveals password if:
          token.reveal_password == true AND identity.password_known == true
    """
    token = (token or "").strip()
    if not token:
        raise HTTPException(status_code=400, detail="token required")

    svc = build_service()
    db, db_err, db_source, db_target = maybe_db()

    ct = svc.store.get_card_token(token)
    if ct is None:
        raise HTTPException(status_code=404, detail="Unknown card token")
    if ct.expires_at_utc <= _now_utc():
        raise HTTPException(status_code=404, detail="Expired card token")

    # build standard card for the resolved user
    try:
        card = svc.user_card(username=ct.username, db=db, recent_minutes=int(recent_minutes))
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown user: {ct.username}")

    # Attach token meta (UI convenience)
    if isinstance(card, dict):
        card["card_token"] = {
            "token": ct.token,
            "expires_at": ct.expires_at_utc.isoformat().replace("+00:00", "Z"),
            "reveal_password": bool(ct.reveal_password),
        }

    # Optional reveal: ONLY if token allows it
    if bool(ct.reveal_password):
        ident = svc.store.get_identity(ct.username)
        if ident is not None and bool(ident.password_known):
            if isinstance(card, dict):
                # Ensure taks_identity exists and include password value
                card["taks_identity"] = {
                    "username": ident.username,
                    "origin": ident.origin,
                    "password_known": bool(ident.password_known),
                    "ctx": ident.ctx or {},
                    "password": {"known": True, "value": ident.password},
                }
        else:
            # keep shape stable if UI wants to show "not available"
            if isinstance(card, dict) and card.get("taks_identity"):
                try:
                    card["taks_identity"]["password"] = {"known": False, "value": None}
                except Exception:
                    pass

    out = {"card": card, "meta": {}}
    out["meta"]["db_attached"] = db is not None
    out["meta"]["db_source"] = db_source
    out["meta"]["db_target"] = db_target
    if db is None and db_err:
        out["meta"]["db_error"] = db_err

    return JSONResponse(out, headers={"cache-control": "no-store, max-age=0", "pragma": "no-cache"})
