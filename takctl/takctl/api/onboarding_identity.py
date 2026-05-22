from __future__ import annotations


def _mumble_users_for_ui(mumble_snapshot):
    out = []
    for u in list((mumble_snapshot or {}).get("users") or []):
        if not isinstance(u, dict):
            continue
        name = str(u.get("name") or "").strip()
        if not name:
            continue
        out.append({
            "name": name,
            "session": u.get("session"),
            "channel": str(u.get("channel_name") or u.get("channel") or "").strip(),
            "connected_now": bool(u.get("connected_now", True)),
        })
    out.sort(key=lambda x: (str(x.get("channel") or ""), str(x.get("name") or ""), str(x.get("session") or "")))
    return out


def _mumble_martine_listeners_for_ui(mumble_snapshot):
    return [
        u for u in _mumble_users_for_ui(mumble_snapshot)
        if str(u.get("name") or "") == "martine-voice"
        or str(u.get("name") or "").startswith("martine-voice-")
    ]

from takctl.onboarding.password_policy import generate_friendly_password


def _gen_strong_password(length: int = 20) -> str:
    """
    Backwards-compatible wrapper. Keep all generated onboarding/user
    passwords on the shared friendly policy.
    """
    n = max(20, min(int(length or 20), 24))
    return generate_friendly_password(min_len=n, max_len=24)

import json
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

from takctl.services.backing_user_store import (
    BackingUserStoreError,
    build_backing_user_store,
    selected_backing_user_store,
)
from takctl.onboarding.policy import Policy
from takctl.config import load_config
from takctl.services.openfire_presence import openfire_for_username
from takctl.onboarding.card_ttl import required_card_link_ttl_sec as _required_card_link_ttl_sec

router = APIRouter(tags=["onboarding"])

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _cfg_bool(name: str, default: bool = False) -> bool:
    raw = str(load_config().get(name, "") or "").strip().lower()
    if not raw:
        return bool(default)
    return raw in ("1", "true", "yes", "y", "on")


def _cert_creation_gate_enabled() -> bool:
    return True

def _user_cert_pem_path(username: str) -> Path:
    u = (username or "").strip()
    return Path("/opt/tak/certs/files/04_USERS") / u / f"{u}.pem"


def _ensure_user_cert(username: str) -> Path | None:
    u = (username or "").strip()
    if not u:
        return None
    if not _cert_creation_gate_enabled():
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



def _card_token_token(ct) -> str:
    if isinstance(ct, dict):
        return str(ct.get("token") or "").strip()
    return str(getattr(ct, "token", "") or "").strip()


def _card_token_username(ct) -> str:
    if isinstance(ct, dict):
        return str(ct.get("username") or ct.get("user") or "").strip()
    return str(getattr(ct, "username", None) or getattr(ct, "user", None) or "").strip()


def _card_token_reveal_password(ct) -> bool:
    if isinstance(ct, dict):
        return bool(ct.get("reveal_password", False))
    return bool(getattr(ct, "reveal_password", False))


def _card_token_expires_at(ct) -> Optional[datetime]:
    if isinstance(ct, dict):
        raw = ct.get("expires_at_utc")
        if raw is None:
            raw = ct.get("expires_at")
    else:
        raw = getattr(ct, "expires_at_utc", None)
        if raw is None:
            raw = getattr(ct, "expires_at", None)

    if raw is None:
        return None

    if isinstance(raw, datetime):
        dt = raw
    else:
        txt = str(raw or "").strip()
        if not txt:
            return None
        if txt.endswith("Z"):
            txt = txt[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(txt)
        except Exception:
            return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _card_token_is_expired(ct) -> bool:
    exp = _card_token_expires_at(ct)
    return bool(exp is not None and exp <= _now_utc())


def _load_card_token_any(svc, token: str):
    t = str(token or "").strip()
    if not t:
        return None

    store = getattr(svc, "store", None)
    cards_dir = getattr(store, "cards_dir", None)

    if cards_dir is not None:
        p = Path(cards_dir) / f"{t}.json"
        if p.exists():
            try:
                raw = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                raw = None
            if isinstance(raw, dict):
                raw.setdefault("token", t)
                return raw

    getter = getattr(store, "get_card_token", None)
    if callable(getter):
        try:
            return getter(t)
        except Exception:
            return None

    return None


def _expired_card_payload(ct) -> Dict[str, Any]:
    exp = _card_token_expires_at(ct)
    out: Dict[str, Any] = {
        "ok": False,
        "error": "expired_card_token",
        "expired": True,
        "token": _card_token_token(ct),
        "username": _card_token_username(ct),
        "reveal_password": _card_token_reveal_password(ct),
    }
    if exp is not None:
        out["expires_at"] = exp.isoformat().replace("+00:00", "Z")
    return out


def _render_expired_card_page(*, base: str, lang: str, username: str, expires_at_utc: Optional[datetime]) -> str:
    sv = str(lang or "sv").strip().lower().startswith("sv")

    title = "Kortet har löpt ut" if sv else "This card has expired"
    body = (
        "Länken är inte längre giltig. Be avsändaren skapa och skicka ett nytt onboardingkort."
        if sv else
        "This link is no longer valid. Ask the sender to issue and send a new onboarding card."
    )
    user_label = "Användare" if sv else "User"
    exp_label = "Giltigt till" if sv else "Valid until"
    help_text = (
        "QR-koder och nedladdningar på gamla kort ska inte längre användas."
        if sv else
        "QR codes and downloads from old cards should no longer be used."
    )
    exp_txt = "okänt" if sv else "unknown"
    if expires_at_utc is not None:
        exp_txt = expires_at_utc.strftime("%Y-%m-%d %H:%M UTC")

    logo_url = f"{base}/assets/branding/node/unit.png"

    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{title}</title>
<style>
body {{
  margin: 0;
  font-family: Arial, Helvetica, sans-serif;
  background: #f3f4f6;
  color: #111827;
}}
.wrap {{
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}}
.card {{
  width: 100%;
  max-width: 760px;
  background: #ffffff;
  border: 1px solid #d1d5db;
  border-radius: 16px;
  overflow: hidden;
  box-shadow: 0 10px 30px rgba(0,0,0,0.08);
}}
.top {{
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 20px 24px;
  background: linear-gradient(180deg, #1f2937 0%, #111827 100%);
  color: #fff;
  border-bottom: 3px solid #b08d2f;
}}
.top img {{
  width: 56px;
  height: 56px;
  object-fit: contain;
  flex: 0 0 auto;
}}
.eyebrow {{
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  opacity: 0.75;
  font-weight: 700;
}}
.title {{
  font-size: 30px;
  line-height: 1.05;
  font-weight: 900;
  margin-top: 4px;
}}
.body {{
  padding: 24px;
}}
.lead {{
  font-size: 18px;
  line-height: 1.45;
  margin: 0 0 18px 0;
}}
.meta {{
  display: grid;
  grid-template-columns: 170px 1fr;
  gap: 10px 12px;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  padding: 16px;
  background: #fafafa;
}}
.label {{
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: #6b7280;
  font-weight: 800;
}}
.value {{
  font-size: 15px;
  word-break: break-word;
}}
.note {{
  margin-top: 18px;
  font-size: 14px;
  color: #4b5563;
}}
.badge {{
  margin-left: auto;
  border: 1px solid rgba(255,255,255,0.28);
  border-radius: 999px;
  padding: 6px 10px;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.08em;
  color: #fde68a;
}}
</style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <div class="top">
        <img src="{logo_url}" alt="Unit logo"/>
        <div>
          <div class="eyebrow">TAKS</div>
          <div class="title">{title}</div>
        </div>
        <div class="badge">EXPIRED</div>
      </div>
      <div class="body">
        <p class="lead">{body}</p>
        <div class="meta">
          <div class="label">{user_label}</div>
          <div class="value">{username or "—"}</div>
          <div class="label">{exp_label}</div>
          <div class="value">{exp_txt}</div>
        </div>
        <div class="note">{help_text}</div>
      </div>
    </div>
  </div>
</body>
</html>"""


def _card_token_json(ct) -> Dict[str, Any]:
    exp = _card_token_expires_at(ct)
    out = {
        "token": _card_token_token(ct),
        "username": _card_token_username(ct),
        "reveal_password": _card_token_reveal_password(ct),
    }
    if exp is not None:
        out["expires_at"] = exp.isoformat().replace("+00:00", "Z")
    return out

def _identity_out(ident, *, password_value: Optional[str] = None) -> Optional[Dict[str, Any]]:
    if ident is None:
        return None

    known = bool(getattr(ident, "password_known", False) or getattr(ident, "password", None))
    value = str(password_value) if (password_value is not None and known) else None

    return {
        "username": str(getattr(ident, "username", "") or ""),
        "origin": str(getattr(ident, "origin", "") or ""),
        "password_known": bool(known),
        "ctx": dict(getattr(ident, "ctx", {}) or {}),
        "identity": dict(getattr(ident, "identity", {}) or {}),
        "password": {
            "known": bool(value is not None),
            "value": value,
        },
    }


def _issue_card_link_base(base: str, svc, *, username: str, reveal_password: bool) -> Dict[str, Any]:
    """
    Background-job compatible card link generator.

    Used by:
      - bulk import
      - future email senders
    """
    ttl = _required_card_link_ttl_sec()
    ct = _create_card_token_compat(
        svc.store,
        username=username,
        ttl_sec=int(ttl),
        reveal_password=bool(reveal_password),
    )

    base = (base or "").rstrip("/")
    return {
        "card_token": _card_token_json(ct),
        "card_url": f"{base}/api/onboarding/cards/{ct.token}",
    }


def _issue_card_link(req: Request, svc, *, username: str, reveal_password: bool) -> Dict[str, Any]:
    """
    Web-request variant.
    """
    base = external_base(req)
    return _issue_card_link_base(
        base,
        svc,
        username=username,
        reveal_password=reveal_password,
    )


class IdentityUpsertIn(BaseModel):
    origin: str = Field(default="marti", description="taks|marti")
    password: Optional[str] = Field(default=None, description="Only stored when origin=taks")
    ctx: Dict[str, Any] = Field(default_factory=dict)


class CardTokenCreateIn(BaseModel):
    reveal_password: bool = Field(default=False)

class EmailLinkIn(BaseModel):
    email: str = Field(default="")
    reveal_password: bool = Field(default=True)

class UserCreateIn(BaseModel):
    password: Optional[str] = Field(default=None)
    backing_user_store: Optional[str] = Field(default=None, description="Override backing user store for this create/update: ldap|userauthfile")
    admin: bool = Field(default=False)
    groups_rw: List[str] = Field(default_factory=list)
    groups_in: List[str] = Field(default_factory=list)
    groups_out: List[str] = Field(default_factory=list)
    ctx: Dict[str, Any] = Field(default_factory=dict)
    configured_callsign: Optional[str] = Field(default=None, description="Canonical configured callsign override; stored as identity.callsign")
    endpoints: Dict[str, Any] = Field(default_factory=dict)
    channels: Optional[List[str]] = Field(default=None, description="Selected Mumble/VX channels. None or [] means derive defaults.")
    reveal_password: bool = Field(default=True)

class IdentityDeriveIn(BaseModel):
    policy_id: str = Field(default="")
    ctx: Dict[str, Any] = Field(default_factory=dict)


class ChannelsDeriveIn(BaseModel):
    policy_id: str = Field(default="")
    ctx: Dict[str, Any] = Field(default_factory=dict)
    selected: Optional[List[str]] = Field(default=None)


@router.post("/onboarding/derive")
def derive_identity(body: IdentityDeriveIn):
    from takctl.onboarding.policy_registry import default_policy_id
    default_pid = default_policy_id()
    policy_id = (body.policy_id or default_pid).strip() or default_pid
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


@router.post("/onboarding/channels/derive")
def derive_channels(body: ChannelsDeriveIn):
    from takctl.onboarding.policy_registry import default_policy_id
    from takctl.onboarding.channels import build_selection_channels, derive_channel_sets

    default_pid = default_policy_id()
    policy_id = (body.policy_id or default_pid).strip() or default_pid
    ctx = dict(body.ctx or {})
    ctx["policy_id"] = policy_id

    channels = build_selection_channels(ctx, selected=body.selected)
    sets = derive_channel_sets(ctx)

    return JSONResponse(
        {
            "ok": True,
            "policy_id": policy_id,
            "ctx": ctx,
            "channels": channels,
            "topology": sets.get("topology") or {},
        },
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
        raise HTTPException(status_code=404, detail=f"user not found in configured backing user store: {u}")

    ident = svc.store.get_identity(u)
    sel = load_selection(u) or {}

    openfire = openfire_for_username(u)
    out = {
        "user": {
            "username": u,
            "groups": list(getattr(tak_user, "groups", []) or []),
        },
        "taks_identity": _identity_out(ident),
        "selection": sel,
        "openfire": openfire,
        "xmpp": openfire,
    }

    return JSONResponse(out, headers={"cache-control": "no-store, max-age=0", "pragma": "no-cache"})


def _cleanup_onboarding_state_for_user(svc, username: str) -> dict:
    json = __import__("json")
    shutil = __import__("shutil")
    selection_mod = __import__("takctl.onboarding.selection", fromlist=["artifact_root"])
    artifact_root = selection_mod.artifact_root

    removed = {
        "identity": False,
        "record": False,
        "card_tokens": 0,
        "artifact_root": False,
        "client_password_fallback": False,
    }

    u = str(username or "").strip()
    store = getattr(svc, "store", None)

    identities_dir = getattr(store, "identities_dir", None)
    if identities_dir is not None:
        fp = identities_dir / f"{u}.json"
        if fp.exists():
            fp.unlink()
            removed["identity"] = True

    users_dir = getattr(store, "users_dir", None)
    if users_dir is not None:
        fp = users_dir / f"{u}.json"
        if fp.exists():
            fp.unlink()
            removed["record"] = True

    cards_dir = getattr(store, "cards_dir", None)
    if cards_dir is not None and cards_dir.exists():
        for cp in sorted(cards_dir.glob("*.json")):
            try:
                raw = json.loads(cp.read_text(encoding="utf-8"))
            except Exception:
                continue
            if str((raw or {}).get("username") or "").strip() != u:
                continue
            try:
                cp.unlink()
                removed["card_tokens"] += 1
            except FileNotFoundError:
                pass

    fallback_pw = Path("/opt/tak/takctl-state/onboarding/identities") / f"{u}.client-password"
    if fallback_pw.exists():
        fallback_pw.unlink()
        removed["client_password_fallback"] = True

    try:
        art = artifact_root(u)
        if art.exists():
            shutil.rmtree(art, ignore_errors=True)
            removed["artifact_root"] = True
    except Exception:
        pass

    return removed


@router.post("/onboarding/users/{username}/delete")
def delete_user(username: str):
    u = (username or "").strip()
    if not u:
        raise HTTPException(status_code=400, detail="username required")

    store_name = selected_backing_user_store()
    svc = build_service(backing_user_store=store_name)

    tak_user = svc.ud.get_user(u)
    if tak_user is None:
        raise HTTPException(status_code=404, detail=f"user not found in configured backing user store: {u}")

    cert_dir = Path("/opt/tak/certs/files/04_USERS") / u
    cert_material_present = any((cert_dir / name).exists() for name in (
        f"{u}.pem",
        f"{u}.key",
        f"{u}.p12",
        f"{u}.modern.p12",
        f"{u}.jks",
        ".client-password",
    ))

    cleanup = _cleanup_onboarding_state_for_user(svc, u)

    writer = build_backing_user_store(store_name)
    try:
        delete_out = writer.delete_user(u)
    except BackingUserStoreError as e:
        raise HTTPException(status_code=500, detail=f"user store delete failed: {e}")

    warning = None
    if cert_material_present:
        warning = (
            "User deleted and TAKS onboarding state removed, but cert revocation/CRL is not wired here yet."
        )

    return JSONResponse(
        {
            "ok": True,
            "username": u,
            "user_deleted": True,
            "user_store_output": delete_out,
            "backing_user_store": store_name,
            "state_cleanup": cleanup,
            "cert_material_present": cert_material_present,
            "warning": warning,
        },
        headers={"cache-control": "no-store, max-age=0", "pragma": "no-cache"},
    )


@router.post("/onboarding/users/{username}/create")
def create_user(req: Request, username: str, body: UserCreateIn):
    u = (username or "").strip()
    if not u:
        raise HTTPException(status_code=400, detail="username required")

    store_name = selected_backing_user_store(body.backing_user_store)
    svc = build_service(backing_user_store=store_name)
    existed = (svc.ud.get_user(u) is not None)

    pw_in = (body.password or "").strip()
    if pw_in:
        pw_to_set: Optional[str] = pw_in
    else:
        pw_to_set = None if existed else generate_friendly_password()

    writer = build_backing_user_store(store_name)
    try:
        writer.ensure_user(
            u,
            password=pw_to_set,
            admin=True if body.admin else None,
            groups=[x for x in (body.groups_rw or []) if str(x).strip()],
            in_groups=[x for x in (body.groups_in or []) if str(x).strip()],
            out_groups=[x for x in (body.groups_out or []) if str(x).strip()],
            append=False,
            remove=False,
            ctx=dict(body.ctx or {}),
        )

        cert_pem = _ensure_user_cert(u)
        if cert_pem is not None:
            writer.ensure_user(
                u,
                certificate_path=str(cert_pem),
                append=True,
                remove=False,
                ctx=dict(body.ctx or {}),
            )
    except BackingUserStoreError as e:
        raise HTTPException(
            status_code=(400 if "Password complexity check failed" in str(e) else 500),
            detail=f"user store write failed: {e}",
        )
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    tak_user = svc.ud.get_user(u)
    if tak_user is None:
        raise HTTPException(status_code=500, detail=f"User not found after create/update in configured backing user store: {u}")

    ctx = dict(body.ctx or {})
    ctx.pop("callsign", None)
    ctx["username"] = u
    configured_callsign = str(body.configured_callsign or "").strip()

    from takctl.onboarding.policy_registry import default_policy_id
    default_pid = default_policy_id()
    policy_id = (ctx.get("policy_id") or default_pid).strip() or default_pid
    ctx["policy_id"] = policy_id

    try:
        from takctl.onboarding.channels import augment_ctx_for_policy
        ctx = augment_ctx_for_policy(ctx)
    except Exception:
        pass

    try:
        pol = Policy(policy_id=policy_id)
        ident = pol.resolve_identity(ctx)
        ident_out = {
            "callsign": configured_callsign or ident.callsign,
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

    try:
        from takctl.onboarding.channels import build_selection_channels

        channel_state = build_selection_channels(ctx, selected=body.channels)
    except Exception as e:
        channel_state = {
            "selected": [str(x).strip() for x in (body.channels or []) if str(x or "").strip()],
            "default": [],
            "available": [str(x).strip() for x in (body.channels or []) if str(x or "").strip()],
            "derive_ok": False,
            "derive_error": f"{type(e).__name__}: {e}",
        }

    sel = {
        "ctx": ctx,
        "endpoints": dict(body.endpoints or {}),
        "channels": channel_state,
    }
    save_selection(u, sel)

    xmpp_bookmarks = None
    try:
        from takctl.onboarding.xmpp_bookmarks import enqueue_user_bookmarks

        xmpp_bookmarks = enqueue_user_bookmarks(
            username=u,
            password=pw_for_store,
            selection=sel,
            identity=ident_out,
            reason="create_user",
        )
    except Exception as e:
        xmpp_bookmarks = {"ok": False, "queued": False, "error": f"{type(e).__name__}: {e}"}

    card_info = _issue_card_link(
        req,
        svc,
        username=u,
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
            "backing_user_store": store_name,
            "taks_identity": _identity_out(
                ident_after,
                password_value=(pw_value if pw_known else None),
            ),
            "selection": sel,
            "xmpp_bookmarks": xmpp_bookmarks,
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
        raise HTTPException(status_code=404, detail=f"user not found in configured backing user store: {username}")

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
        raise HTTPException(status_code=404, detail=f"user not found in configured backing user store: {username}")

    try:
        out = _issue_card_link(
            req,
            svc,
            username=username,
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
        raise HTTPException(status_code=404, detail=f"user not found in configured backing user store: {username}")

    try:
        card_info = _issue_card_link(
            req,
            svc,
            username=username,
            reveal_password=bool(body.reveal_password),
        )
        ident = svc.store.get_identity(username)
        ident_payload = {}
        try:
            ident_payload.update(dict(getattr(ident, "ctx", None) or {}))
        except Exception:
            pass
        try:
            ident_payload.update(dict(getattr(ident, "identity", None) or {}))
        except Exception:
            pass

        email_status = send_onboarding_email(
            to_addr=email,
            username=username,
            card_url=str(card_info.get("card_url") or ""),
            lang=str(load_config().get("language", "sv") or "sv"),
            ident=ident_payload,
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


@router.get("/onboarding/users/{username}/voice-live")
def voice_live(username: str, recent_minutes: int = Query(120, ge=1, le=24 * 60)):
    u = (username or "").strip()
    if not u:
        raise HTTPException(status_code=400, detail="username required")

    svc = build_service()

    tak_user = svc.ud.get_user(u)
    if tak_user is None:
        raise HTTPException(status_code=404, detail=f"user not found in configured backing user store: {u}")

    db, _db_err, _db_source, _db_target = maybe_db()

    try:
        card = svc.user_card(username=u, db=db, recent_minutes=int(recent_minutes))
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown user: {u}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"voice live failed: {type(e).__name__}: {e}")

    try:
        from takctl.services.mumble_live import snapshot_mumble_live

        mumble_snapshot = snapshot_mumble_live()
    except Exception as e:
        mumble_snapshot = {
            "server": {"host": None, "port": None, "connected": False},
            "raw_counts": {"channels": 0, "users": 0, "devices": 0},
            "users": [],
            "error": f"snapshot_mumble_live failed: {type(e).__name__}: {e}",
        }

    voice = (card or {}).get("voice")
    if not isinstance(voice, dict):
        voice = {
            "ok": False,
            "username": u,
            "server": {"host": None, "port": None, "connected": False},
            "snapshot_meta": {"source": "onboarding_identity.voice_live", "generated_at": None},
            "error": "voice data missing from user_card",
            "user": {
                "callsign": str(((card or {}).get("header") or {}).get("callsign") or u),
                "connected_now": False,
                "channel_names": [],
                "matched_user_names": [],
                "header_matches": [],
            },
            "devices": [],
            "raw_counts": {"channels": 0, "users": 0, "devices": 0},
            "voice_users": _mumble_users_for_ui(mumble_snapshot),
            "martine_voice_listeners": _mumble_martine_listeners_for_ui(mumble_snapshot),
        }

    if isinstance(voice, dict):
        voice = dict(voice)
        voice["voice_users"] = _mumble_users_for_ui(mumble_snapshot)
        voice["martine_voice_listeners"] = _mumble_martine_listeners_for_ui(mumble_snapshot)
        if not voice.get("raw_counts"):
            voice["raw_counts"] = dict((mumble_snapshot or {}).get("raw_counts") or {})
        if (mumble_snapshot or {}).get("error") and not voice.get("error"):
            voice["error"] = (mumble_snapshot or {}).get("error")

    return JSONResponse(
        voice,
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

    ct = _load_card_token_any(svc, token)
    if ct is None:
        raise HTTPException(status_code=404, detail="Unknown card token")

    if _card_token_is_expired(ct):
        return JSONResponse(
            _expired_card_payload(ct),
            status_code=410,
            headers={"cache-control": "no-store, max-age=0", "pragma": "no-cache"},
        )

    username = _card_token_username(ct)
    if not username:
        raise HTTPException(status_code=404, detail="Unknown card token")

    db, _db_err, _db_source, _db_target = maybe_db()

    try:
        card = svc.user_card(username=username, db=db, recent_minutes=int(recent_minutes))
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown user: {username}")

    if isinstance(card, dict):
        card["card_token"] = _card_token_json(ct)

    if bool(_card_token_reveal_password(ct)):
        ident = svc.store.get_identity(username)
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

    return JSONResponse(
        card,
        headers={"cache-control": "no-store, max-age=0", "pragma": "no-cache"},
    )

@router.get("/onboarding/cards/{token}")

def onboarding_card_html(req: Request, token: str):
    svc = build_service()

    try:
        lang = str(load_config().get("language", "sv") or "sv").strip().lower()
    except Exception:
        lang = "sv"

    base = external_base(req).rstrip("/")

    ct = _load_card_token_any(svc, token)
    if not ct:
        html = _render_expired_card_page(
            base=base,
            lang=lang,
            username="",
            expires_at_utc=None,
        )
        return HTMLResponse(
            html,
            status_code=410,
            headers={"cache-control": "no-store, max-age=0", "pragma": "no-cache"},
        )

    username = _card_token_username(ct)
    if not username:
        html = _render_expired_card_page(
            base=base,
            lang=lang,
            username="",
            expires_at_utc=_card_token_expires_at(ct),
        )
        return HTMLResponse(
            html,
            status_code=410,
            headers={"cache-control": "no-store, max-age=0", "pragma": "no-cache"},
        )

    exp = _card_token_expires_at(ct)

    if _card_token_is_expired(ct):
        html = _render_expired_card_page(
            base=base,
            lang=lang,
            username=username,
            expires_at_utc=exp,
        )
        return HTMLResponse(
            html,
            status_code=410,
            headers={"cache-control": "no-store, max-age=0", "pragma": "no-cache"},
        )

    db, _db_err, _db_source, _db_target = maybe_db()

    try:
        card = svc.user_card(username=username, db=db, recent_minutes=120)
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

    reveal = bool(_card_token_reveal_password(ct))

    try:
        cfg_reveal_user = str(load_config().get("reveal_user_pass_on_soldier_card", "") or "").strip().lower() in ("1", "true", "yes", "y", "on")
    except Exception:
        cfg_reveal_user = False

    try:
        cfg_reveal_default = str(load_config().get("reveal_password_default", "") or "").strip().lower() in ("1", "true", "yes", "y", "on")
    except Exception:
        cfg_reveal_default = False

    reveal = bool(reveal or cfg_reveal_user or cfg_reveal_default)

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

