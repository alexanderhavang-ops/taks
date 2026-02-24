from __future__ import annotations


def _gen_strong_password(length: int = 20) -> str:
    """
    Generate a Marti-compliant password.

    Rule (as enforced by UserManager.jar in your setup):
      - min 15 chars
      - at least 1 uppercase, 1 lowercase, 1 number
      - at least 1 special character from:
        [-_!@#$%^&*(){}[]+=~`|:;<>,./?]
    """
    import secrets

    specials = r"-_!@#$%^&*(){}[]+=~`|:;<>,./?"
    uppers = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    lowers = "abcdefghijklmnopqrstuvwxyz"
    digits = "0123456789"

    n = max(int(length), 15)

    # Ensure required categories
    chars = [
        secrets.choice(uppers),
        secrets.choice(lowers),
        secrets.choice(digits),
        secrets.choice(specials),
    ]

    alphabet = uppers + lowers + digits + specials
    while len(chars) < n:
        chars.append(secrets.choice(alphabet))

    # Fisher–Yates shuffle
    for i in range(len(chars) - 1, 0, -1):
        j = secrets.randbelow(i + 1)
        chars[i], chars[j] = chars[j], chars[i]

    return "".join(chars)

from datetime import datetime, timezone
from typing import Any, Dict, Optional, List

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, HTMLResponse
from pydantic import BaseModel, Field

from takctl.onboarding.onboarding_db import maybe_db
from takctl.onboarding.service_builder import build_service
from takctl.onboarding.http import external_base
from takctl.onboarding.selection import load_selection, save_selection
from takctl.onboarding.pages_soldier import render_soldier_card_page

from takctl.services.usermgr import UserMgrService, UserMgrError
from takctl.onboarding.policy import Policy

import secrets

router = APIRouter(tags=["onboarding"])


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class IdentityUpsertIn(BaseModel):
    origin: str = Field(default="marti", description="taks|marti")
    password: Optional[str] = Field(default=None, description="Only stored when origin=taks")
    ctx: Dict[str, Any] = Field(default_factory=dict)


class CardTokenCreateIn(BaseModel):
    ttl_sec: int = Field(default=3600, ge=60, le=7 * 24 * 3600)
    reveal_password: bool = Field(default=False)


# ---------------------------
# NEW: user creation endpoint
# ---------------------------

class UserCreateIn(BaseModel):
    # If omitted, we generate a strong password.
    password: Optional[str] = Field(default=None)

    # If true, pass -A to usermod.
    admin: bool = Field(default=False)

    # Group lists map to UserManager.jar flags -g/-ig/-og
    groups_rw: List[str] = Field(default_factory=list)
    groups_in: List[str] = Field(default_factory=list)
    groups_out: List[str] = Field(default_factory=list)

    # Persisted ctx used by policy.conf. If missing, we still store it (empty) and policy uses defaults.
    ctx: Dict[str, Any] = Field(default_factory=dict)

    # Persist selection in the same shape as Generate page uses.
    # Keep defaults aligned with UI.
    paths: Dict[str, bool] = Field(default_factory=lambda: {"B": True, "itak": True, "wintak": True})
    endpoints: Dict[str, Any] = Field(default_factory=dict)

    # Card token behavior
    ttl_sec: int = Field(default=600, ge=60, le=7 * 24 * 3600)
    reveal_password: bool = Field(default=True)


@router.post("/onboarding/users/{username}/create")
def create_user(req: Request, username: str, body: UserCreateIn):
    """
    CREATE / ENSURE user in authoritative TAK store (UserAuthenticationFile.xml via UserManager.jar),
    then persist TAKS-owned overlay + selection + issue a shareable card token.

    This is the "new architecture" flow:
      1) authoritative user exists (jar)
      2) taks_identity exists (origin=taks + password_known + ctx + derived identity)
      3) selection.json exists (ctx/paths/endpoints)
      4) token -> card_url
    """
    u = (username or "").strip()
    if not u:
        raise HTTPException(status_code=400, detail="username required")

    svc = build_service()

    # Generate password if not provided
    pw = (body.password or "").strip() or _gen_strong_password(20)
    # 1) Create / update authoritative user (jar writes UserAuthenticationFile.xml)
    um = UserMgrService()
    try:
        # NOTE: we are conservative: we SET password explicitly and set groups exactly as provided.
        # If you want append/remove semantics later, we can add flags.
        um.user_set(
            u,
            password=pw,
            admin=True if body.admin else None,
            groups=[x for x in (body.groups_rw or []) if str(x).strip()],
            in_groups=[x for x in (body.groups_in or []) if str(x).strip()],
            out_groups=[x for x in (body.groups_out or []) if str(x).strip()],
            append=False,
            remove=False,
        )
    except UserMgrError as e:
        raise HTTPException(status_code=(400 if "Password complexity check failed" in str(e) else 500), detail=f"UserManager failed: {e}")

    # Re-check existence via authoritative directory (read-only observer)
    tak_user = svc.ud.get_user(u)
    if tak_user is None:
        raise HTTPException(status_code=500, detail=f"User not found after create in UserAuthenticationFile.xml: {u}")

    # 2) Derive identity via policy grammar and persist taks_identity overlay (includes password)
    ctx = dict(body.ctx or {})
    policy_id = (ctx.get("policy_id") or "hemvarnet").strip() or "hemvarnet"
    try:
        pol = Policy(policy_id=policy_id)
        ident = pol.resolve_identity(ctx)
        ident_out = {
            "callsign": ident.callsign,
            "team": ident.team,
            "atak_role_type": getattr(ident, "atak_role_type", None),
        }
    except Exception as e:
        # Don’t fail user creation on policy mistakes; store ctx and leave identity empty.
        ident_out = {}
        ctx = dict(ctx)
        ctx.setdefault("_policy_error", str(e))

    svc.store.upsert_identity(
        username=u,
        origin="taks",
        ctx=ctx,
        identity=ident_out,
        password=pw,
    )

    # 3) Persist selection.json (same shape Generate page expects)
    sel = {
        "ctx": ctx,
        "paths": dict(body.paths or {"B": True, "itak": True, "wintak": True}),
        "endpoints": dict(body.endpoints or {}),
    }
    save_selection(u, sel)

    # 4) Issue a shareable card token (by default: reveal password)
    ct = svc.store.create_card_token(username=u, ttl_sec=int(body.ttl_sec), reveal_password=bool(body.reveal_password))

    base = external_base(req).rstrip("/")
    card_url = f"{base}/api/onboarding/cards/{ct.token}"

    return JSONResponse(
        {
            "user": {
                "username": u,
                "groups": list(getattr(tak_user, "groups", []) or []),
            },
            "taks_identity": {
                "origin": "taks",
                "password_known": True,
                "ctx": ctx,
                "identity": ident_out,
                # This endpoint is auth-gated, so we return the password for immediate copy/paste.
                "password": {"known": True, "value": pw},
            },
            "selection": sel,
            "card_token": {
                "token": ct.token,
                "username": ct.username,
                "expires_at": ct.expires_at_utc.isoformat().replace("+00:00", "Z"),
                "reveal_password": bool(ct.reveal_password),
            },
            "card_url": card_url,
        },
        headers={"cache-control": "no-store, max-age=0", "pragma": "no-cache"},
    )


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
        raise HTTPException(
            status_code=500,
            detail="Onboarding store missing card-token creator (create_card_token/upsert_card_token)",
        )

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
                card["taks_identity"] = {
                    "username": ident.username,
                    "origin": ident.origin,
                    "password_known": bool(ident.password_known),
                    "ctx": ident.ctx or {},
                    "identity": ident.identity or {},
                    "password": {"known": True, "value": ident.password},
                }
        else:
            if isinstance(card, dict) and card.get("taks_identity"):
                # keep overlay but hide value
                try:
                    card["taks_identity"]["password"] = {"known": False, "value": None}
                except Exception:
                    pass

    return JSONResponse(card, headers={"cache-control": "no-store, max-age=0", "pragma": "no-cache"})


@router.get("/onboarding/cards/{token}")
def onboarding_card_html(req: Request, token: str):
    """
    Public, shareable soldier card (NO web auth).
    """
    svc = build_service()

    ct = svc.store.get_card_token(token)
    if not ct:
        raise HTTPException(status_code=404, detail="Not Found")

    username = getattr(ct, "username", None) or getattr(ct, "user", None) or ""
    username = str(username).strip()
    if not username:
        raise HTTPException(status_code=404, detail="Not Found")

    # Groups + identity: use service card (best effort, DB optional)
    try:
        card = svc.user_card(username=username, db=None, recent_minutes=120)
    except Exception:
        card = {}

    tak_user = (card.get("tak_user") or {}) if isinstance(card, dict) else {}
    groups = tak_user.get("groups") or []
    if not isinstance(groups, list):
        groups = []

    ident = (card.get("taks_identity") or None) if isinstance(card, dict) else None
    sel = load_selection(username) or {}

    base = external_base(req).rstrip("/")
    exp = getattr(ct, "expires_at_utc", None) or getattr(ct, "expires_at", None)
    reveal = bool(getattr(ct, "reveal_password", False))

    html = render_soldier_card_page(
        username=username,
        groups=groups,
        base=base,
        sel=sel,
        ident=ident,
        token=str(token),
        expires_at_utc=exp,
        reveal_password=reveal,
    )
    return HTMLResponse(html, headers={"cache-control": "no-store, max-age=0", "pragma": "no-cache"})
