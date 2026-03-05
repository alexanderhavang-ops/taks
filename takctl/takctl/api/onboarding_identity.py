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
    # If omitted:
    #  - if user does NOT exist => we generate a strong password and set it
    #  - if user exists        => we do NOT change password
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


# ---------------------------
# NEW: derive identity preview (policy-driven)
# ---------------------------

class IdentityDeriveIn(BaseModel):
    policy_id: str = Field(default="hemvarnet")
    ctx: Dict[str, Any] = Field(default_factory=dict)


@router.post("/onboarding/derive")
def derive_identity(body: IdentityDeriveIn):
    """
    Preview derived identity (callsign/team/atak_role_type) from policy.conf + grammar.

    This is used by the web UI to show computed read-only fields live.
    """
    policy_id = (body.policy_id or "hemvarnet").strip() or "hemvarnet"
    ctx = dict(body.ctx or {})
    try:
        pol = Policy(policy_id=policy_id)
        ident = pol.resolve_identity(ctx)

        identity = {
            "callsign": ident.callsign,
            "team": ident.team,
            "atak_role_type": getattr(ident, "atak_role_type", None),
        }
        # Optional debug/UX fields (read-only)
        v = getattr(ident, "callsign_variants", None)
        if isinstance(v, dict) and v:
            identity["callsign_variants"] = v
        eff = getattr(ident, "callsign_policy_effective", None)
        if eff:
            identity["callsign_policy_effective"] = eff
        return JSONResponse(
            {
                "ok": True,
                "policy_id": policy_id,
                "ctx": ctx,
                "identity": identity,
            },
            headers={"cache-control": "no-store, max-age=0", "pragma": "no-cache"},
        )
    except Exception as e:
        return JSONResponse(
            {
                "ok": False,
                "policy_id": policy_id,
                "ctx": ctx,
                "error": f"{type(e).__name__}: {e}",
            },
            status_code=400,
            headers={"cache-control": "no-store, max-age=0", "pragma": "no-cache"},
        )


# ---------------------------
# NEW: fetch one user (for Edit UI)
# ---------------------------

@router.get("/onboarding/users/{username}")
def get_user(username: str):
    """
    Fetch a single user model for the web UI "Edit" flow.

    Returns:
      - user: authoritative groups (from UserAuthenticationFile.xml observer)
      - taks_identity: overlay ctx/identity (password not revealed here)
      - selection: selection.json (ctx + paths + endpoints)
    """
    u = (username or "").strip()
    if not u:
        raise HTTPException(status_code=400, detail="username required")

    svc = build_service()

    tak_user = svc.ud.get_user(u)
    if tak_user is None:
        raise HTTPException(status_code=404, detail=f"user not found in UserAuthenticationFile.xml: {u}")

    ident = svc.store.get_identity(u)
    sel = load_selection(u) or {}

    out = {
        "user": {
            "username": u,
            "groups": list(getattr(tak_user, "groups", []) or []),
        },
        "taks_identity": None,
        "selection": sel,
    }

    if ident is not None:
        out["taks_identity"] = {
            "username": ident.username,
            "origin": ident.origin,
            "password_known": bool(getattr(ident, "password_known", False)),
            "ctx": ident.ctx or {},
            "identity": getattr(ident, "identity", None) or {},
            # DO NOT reveal password here (Edit UI doesn't need it)
            "password": {"known": False, "value": None},
        }

    return JSONResponse(out, headers={"cache-control": "no-store, max-age=0", "pragma": "no-cache"})


@router.post("/onboarding/users/{username}/create")
def create_user(req: Request, username: str, body: UserCreateIn):
    """
    CREATE / ENSURE user in authoritative TAK store (UserAuthenticationFile.xml via UserManager.jar),
    then persist TAKS-owned overlay + selection + issue a shareable card token.

    Semantics:
      - If user doesn't exist and password omitted => generate password and set it.
      - If user exists and password omitted => do NOT change password.
    """
    u = (username or "").strip()
    if not u:
        raise HTTPException(status_code=400, detail="username required")

    svc = build_service()

    # Determine whether user exists BEFORE usermod
    existed = (svc.ud.get_user(u) is not None)

    pw_in = (body.password or "").strip()
    if pw_in:
        pw_to_set: Optional[str] = pw_in
    else:
        pw_to_set = None if existed else _gen_strong_password(20)

    # 1) Create / update authoritative user (jar writes UserAuthenticationFile.xml)
    um = UserMgrService()
    try:
        um.user_set(
            u,
            password=pw_to_set,  # None => do not change pw
            admin=True if body.admin else None,
            groups=[x for x in (body.groups_rw or []) if str(x).strip()],
            in_groups=[x for x in (body.groups_in or []) if str(x).strip()],
            out_groups=[x for x in (body.groups_out or []) if str(x).strip()],
            append=False,
            remove=False,
        )
    except UserMgrError as e:
        raise HTTPException(
            status_code=(400 if "Password complexity check failed" in str(e) else 500),
            detail=f"UserManager failed: {e}",
        )

    # Re-check existence via authoritative directory (read-only observer)
    tak_user = svc.ud.get_user(u)
    if tak_user is None:
        raise HTTPException(status_code=500, detail=f"User not found after create/update in UserAuthenticationFile.xml: {u}")

    # 2) Derive identity via policy grammar and persist taks_identity overlay
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
        ident_out = {}
        ctx = dict(ctx)
        ctx.setdefault("_policy_error", str(e))

    # Preserve existing stored password if we didn't change it and it was known
    existing_ident = svc.store.get_identity(u)
    pw_for_store: Optional[str] = None
    if pw_to_set is not None:
        pw_for_store = pw_to_set
    else:
        # unchanged: keep previous known password if any
        if existing_ident is not None and bool(getattr(existing_ident, "password_known", False)):
            pw_for_store = getattr(existing_ident, "password", None)

    svc.store.upsert_identity(
        username=u,
        origin="taks",
        ctx=ctx,
        identity=ident_out,
        password=pw_for_store,
    )

    # 3) Persist selection.json (same shape Generate page expects)
    sel = {
        "ctx": ctx,
        "paths": dict(body.paths or {"B": True, "itak": True, "wintak": True}),
        "endpoints": dict(body.endpoints or {}),
    }
    save_selection(u, sel)

    # 4) Issue a shareable card token
    ct = svc.store.create_card_token(username=u, ttl_sec=int(body.ttl_sec), reveal_password=bool(body.reveal_password))

    base = external_base(req).rstrip("/")
    card_url = f"{base}/api/onboarding/cards/{ct.token}"

    # Decide what to return about password:
    # - If we set it now, we can reveal it (for create flow).
    # - If unchanged, we do not know it (unless it was previously known and stored).
    pw_known = pw_for_store is not None and bool(getattr(svc.store.get_identity(u), "password_known", False))
    pw_value = pw_for_store if (pw_to_set is not None) else (pw_for_store if pw_known else None)

    return JSONResponse(
        {
            "user": {
                "username": u,
                "groups": list(getattr(tak_user, "groups", []) or []),
            },
            "taks_identity": {
                "origin": "taks",
                "password_known": bool(pw_known),
                "ctx": ctx,
                "identity": ident_out,
                "password": {"known": bool(pw_known), "value": pw_value},
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
        identity={},  # reserved for future
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

    try:
        card = svc.user_card(username=ct.username, db=db, recent_minutes=int(recent_minutes))
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown user: {ct.username}")

    if isinstance(card, dict):
        card["card_token"] = {
            "token": ct.token,
            "expires_at": ct.expires_at_utc.isoformat().replace("+00:00", "Z"),
            "reveal_password": bool(ct.reveal_password),
        }

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

    # Pull lifecycle/groups from canonical card model (best effort, DB optional)
    try:
        card = svc.user_card(username=username, db=None, recent_minutes=120)
    except Exception:
        card = {}

    lifecycle = card.get("lifecycle") if isinstance(card, dict) else None

    groups = []
    if isinstance(card, dict):
        m = card.get("marti") or {}
        if isinstance(m, dict) and isinstance(m.get("groups"), list):
            groups = m.get("groups") or []
    if not isinstance(groups, list):
        groups = []

    ident = svc.store.get_identity(username)
    sel = load_selection(username) or {}

    base = external_base(req).rstrip("/")
    exp = getattr(ct, "expires_at_utc", None) or getattr(ct, "expires_at", None)
    reveal = bool(getattr(ct, "reveal_password", False))

    lang = (req.query_params.get("lang") or "").strip().lower()



    html = render_soldier_card_page(
        lang=lang,
        username=username,
        groups=groups,
        base=base,
        sel=sel,
        ident=ident,
        token=token,
        expires_at_utc=exp,
        reveal_password=reveal,
        lifecycle=lifecycle,
    )
    return HTMLResponse(html, headers={"cache-control": "no-store, max-age=0", "pragma": "no-cache"})
