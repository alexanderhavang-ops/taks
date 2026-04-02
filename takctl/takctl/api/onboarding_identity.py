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

    chars = [
        secrets.choice(uppers),
        secrets.choice(lowers),
        secrets.choice(digits),
        secrets.choice(specials),
    ]

    alphabet = uppers + lowers + digits + specials
    while len(chars) < n:
        chars.append(secrets.choice(alphabet))

    for i in range(len(chars) - 1, 0, -1):
        j = secrets.randbelow(i + 1)
        chars[i], chars[j] = chars[j], chars[i]

    return "".join(chars)


from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, List

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, HTMLResponse
from pydantic import BaseModel, Field

from takctl.onboarding.onboarding_db import maybe_db
from takctl.onboarding.service_builder import build_service
from takctl.onboarding.http import external_base
from takctl.onboarding.selection import load_selection, save_selection
from takctl.onboarding.pages_soldier import render_soldier_card_page
from takctl.onboarding.emailer import send_onboarding_email, is_valid_email

from takctl.services.usermgr import UserMgrService, UserMgrError
from takctl.onboarding.policy import Policy
from takctl.config import load_config

router = APIRouter(tags=["onboarding"])


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _cfg_bool(name: str, default: bool = False) -> bool:
    raw = str(load_config().get(name, "") or "").strip().lower()
    if not raw:
        return bool(default)
    return raw in ("1", "true", "yes", "y", "on")


def _onboarding_mode() -> str:
    raw = str(load_config().get("onboarding_mode", "") or "").strip().lower()
    if raw in ("auto-enroll", "cert-creation"):
        return raw
    return "cert-creation" if _cfg_bool("create_cert_with_user", False) else "auto-enroll"


def _user_cert_pem_path(username: str) -> Path:
    u = (username or "").strip()
    return Path("/opt/tak/certs/files/04_USERS") / u / f"{u}.pem"


def _ensure_user_cert(username: str) -> Path | None:
    u = (username or "").strip()
    if not u:
        return None
    if _onboarding_mode() != "cert-creation":
        return None

    cert_pem = _user_cert_pem_path(u)
    if cert_pem.exists():
        return cert_pem

    import subprocess

    helper = "/opt/tak/tools/takctl/bin/takctl-makecert"
    p = subprocess.run(
        ["sudo", "-n", helper, "client", u],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    out = (p.stdout or "").strip()
    if p.returncode != 0:
        raise RuntimeError(out or f"failed to create cert for {u}")
    if not cert_pem.exists():
        raise RuntimeError(f"cert helper succeeded but PEM missing: {cert_pem}")
    return cert_pem


def _create_card_token_compat(store, *, username: str, ttl_sec: int, reveal_password: bool):
    """
    Store API drift guard:
      - create_card_token(...)
      - upsert_card_token(...)
    """
    if hasattr(store, "create_card_token"):
        return store.create_card_token(
            username=username,
            ttl_sec=int(ttl_sec),
            reveal_password=bool(reveal_password),
        )

    if hasattr(store, "upsert_card_token"):
        return store.upsert_card_token(
            username=username,
            ttl_sec=int(ttl_sec),
            reveal_password=bool(reveal_password),
        )

    raise RuntimeError(
        "Onboarding store missing card-token creator (create_card_token/upsert_card_token)"
    )


def _card_token_json(ct) -> Dict[str, Any]:
    return {
        "token": ct.token,
        "username": ct.username,
        "expires_at": ct.expires_at_utc.isoformat().replace("+00:00", "Z"),
        "reveal_password": bool(ct.reveal_password),
    }


def _issue_card_link_base(base: str, svc, *, username: str, ttl_sec: int, reveal_password: bool) -> Dict[str, Any]:
    """
    Background-job compatible card link generator.

    Used by:
      - bulk import
      - future email senders
    """
    ct = _create_card_token_compat(
        svc.store,
        username=username,
        ttl_sec=int(ttl_sec),
        reveal_password=bool(reveal_password),
    )

    base = (base or "").rstrip("/")
    return {
        "card_token": _card_token_json(ct),
        "card_url": f"{base}/api/onboarding/cards/{ct.token}",
    }


def _issue_card_link(req: Request, svc, *, username: str, ttl_sec: int, reveal_password: bool) -> Dict[str, Any]:
    """
    Web-request variant.
    """
    base = external_base(req)
    return _issue_card_link_base(
        base,
        svc,
        username=username,
        ttl_sec=ttl_sec,
        reveal_password=reveal_password,
    )


class IdentityUpsertIn(BaseModel):
    origin: str = Field(default="marti", description="taks|marti")
    password: Optional[str] = Field(default=None, description="Only stored when origin=taks")
    ctx: Dict[str, Any] = Field(default_factory=dict)


class CardTokenCreateIn(BaseModel):
    ttl_sec: int = Field(default=3600, ge=60, le=7 * 24 * 3600)
    reveal_password: bool = Field(default=False)


class EmailLinkIn(BaseModel):
    email: str = Field(default="")
    ttl_sec: int = Field(default=3600, ge=60, le=7 * 24 * 3600)
    reveal_password: bool = Field(default=True)


class UserCreateIn(BaseModel):
    password: Optional[str] = Field(default=None)
    admin: bool = Field(default=False)
    groups_rw: List[str] = Field(default_factory=list)
    groups_in: List[str] = Field(default_factory=list)
    groups_out: List[str] = Field(default_factory=list)
    ctx: Dict[str, Any] = Field(default_factory=dict)
    endpoints: Dict[str, Any] = Field(default_factory=dict)
    ttl_sec: int = Field(default=600, ge=60, le=7 * 24 * 3600)
    reveal_password: bool = Field(default=True)


class IdentityDeriveIn(BaseModel):
    policy_id: str = Field(default="hemvarnet")
    ctx: Dict[str, Any] = Field(default_factory=dict)


@router.post("/onboarding/derive")
def derive_identity(body: IdentityDeriveIn):
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


@router.get("/onboarding/users/{username}")
def get_user(username: str):
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
            "password": {"known": False, "value": None},
        }

    return JSONResponse(out, headers={"cache-control": "no-store, max-age=0", "pragma": "no-cache"})


@router.post("/onboarding/users/{username}/create")
def create_user(req: Request, username: str, body: UserCreateIn):
    u = (username or "").strip()
    if not u:
        raise HTTPException(status_code=400, detail="username required")

    svc = build_service()
    existed = (svc.ud.get_user(u) is not None)

    pw_in = (body.password or "").strip()
    if pw_in:
        pw_to_set: Optional[str] = pw_in
    else:
        pw_to_set = None if existed else _gen_strong_password(20)

    um = UserMgrService()
    try:
        um.user_set(
            u,
            password=pw_to_set,
            admin=True if body.admin else None,
            groups=[x for x in (body.groups_rw or []) if str(x).strip()],
            in_groups=[x for x in (body.groups_in or []) if str(x).strip()],
            out_groups=[x for x in (body.groups_out or []) if str(x).strip()],
            append=False,
            remove=False,
        )

        cert_pem = _ensure_user_cert(u)
        if cert_pem is not None:
            um.user_set(
                u,
                certificate_path=str(cert_pem),
                append=False,
                remove=False,
            )
    except UserMgrError as e:
        raise HTTPException(
            status_code=(400 if "Password complexity check failed" in str(e) else 500),
            detail=f"UserManager failed: {e}",
        )
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    tak_user = svc.ud.get_user(u)
    if tak_user is None:
        raise HTTPException(status_code=500, detail=f"User not found after create/update in UserAuthenticationFile.xml: {u}")

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

    existing_ident = svc.store.get_identity(u)
    pw_for_store: Optional[str] = None
    if pw_to_set is not None:
        pw_for_store = pw_to_set
    else:
        if existing_ident is not None and bool(getattr(existing_ident, "password_known", False)):
            pw_for_store = getattr(existing_ident, "password", None)

    svc.store.upsert_identity(
        username=u,
        origin="taks",
        ctx=ctx,
        identity=ident_out,
        password=pw_for_store,
    )

    sel = {
        "ctx": ctx,
        "endpoints": dict(body.endpoints or {}),
    }
    save_selection(u, sel)

    card_info = _issue_card_link(
        req,
        svc,
        username=u,
        ttl_sec=int(body.ttl_sec),
        reveal_password=bool(body.reveal_password),
    )

    ident_after = svc.store.get_identity(u)
    pw_known = pw_for_store is not None and bool(getattr(ident_after, "password_known", False))
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
            **card_info,
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

    u = svc.ud.get_user(username)
    if u is None:
        raise HTTPException(status_code=404, detail=f"user not found in UserAuthenticationFile.xml: {username}")

    ident = svc.store.upsert_identity(
        username=username,
        origin=origin,
        ctx=(body.ctx or {}),
        identity={},
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
def create_card_token(req: Request, username: str, body: CardTokenCreateIn):
    username = (username or "").strip()
    if not username:
        raise HTTPException(status_code=400, detail="username required")

    svc = build_service()

    u = svc.ud.get_user(username)
    if u is None:
        raise HTTPException(status_code=404, detail=f"user not found in UserAuthenticationFile.xml: {username}")

    try:
        out = _issue_card_link(
            req,
            svc,
            username=username,
            ttl_sec=int(body.ttl_sec),
            reveal_password=bool(body.reveal_password),
        )
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    return JSONResponse(
        out,
        headers={"cache-control": "no-store, max-age=0", "pragma": "no-cache"},
    )


@router.post("/onboarding/users/{username}/email-link")
def email_link(req: Request, username: str, body: EmailLinkIn):
    username = (username or "").strip()
    if not username:
        raise HTTPException(status_code=400, detail="username required")

    email = (body.email or "").strip()
    if not email:
        raise HTTPException(status_code=400, detail="email required")
    if not is_valid_email(email):
        raise HTTPException(status_code=400, detail=f"invalid email address: {email!r}")

    svc = build_service()

    u = svc.ud.get_user(username)
    if u is None:
        raise HTTPException(status_code=404, detail=f"user not found in UserAuthenticationFile.xml: {username}")

    try:
        card_info = _issue_card_link(
            req,
            svc,
            username=username,
            ttl_sec=int(body.ttl_sec),
            reveal_password=bool(body.reveal_password),
        )
        email_status = send_onboarding_email(
            to_addr=email,
            username=username,
            card_url=str(card_info.get("card_url") or ""),
            lang=str(load_config().get("language", "sv") or "sv"),
        )

        sel = load_selection(username) or {}
        if not isinstance(sel, dict):
            sel = {}
        sel["last_onboarding_email"] = {
            "sent_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "email": email,
            "card_url": str(card_info.get("card_url") or ""),
            "print_mode": "cards",
            "reveal_password": bool(body.reveal_password),
            "delivery": str((email_status or {}).get("delivery") or ""),
        }
        save_selection(username, sel)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"email send failed: {e}")

    return JSONResponse(
        {
            "username": username,
            "email": email,
            **card_info,
            "email_status": email_status,
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
    svc = build_service()

    ct = svc.store.get_card_token(token)
    if not ct:
        raise HTTPException(status_code=404, detail="Not Found")

    username = getattr(ct, "username", None) or getattr(ct, "user", None) or ""
    username = str(username).strip()
    if not username:
        raise HTTPException(status_code=404, detail="Not Found")

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

    try:
        lang = str(load_config().get("language", "sv") or "sv").strip().lower()
    except Exception:
        lang = "sv"

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

