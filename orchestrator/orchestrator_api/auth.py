from __future__ import annotations

import os
import hmac
import hashlib
import base64
import time
from typing import Optional, Tuple

from fastapi import Request, HTTPException


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _sign(msg: bytes, secret: str) -> str:
    return _b64(hmac.new(secret.encode(), msg, hashlib.sha256).digest())


def make_token(user: str, secret: str, ttl: int = 12 * 3600) -> str:
    exp = int(time.time()) + ttl
    payload = f"{user}|{exp}".encode()
    return _b64(payload) + "." + _sign(payload, secret)


def verify_token(tok: str, secret: str) -> bool:
    try:
        a, sig = tok.split(".", 1)
        payload = _unb64(a)
        _user, exp = payload.decode().split("|", 1)
        if int(exp) < time.time():
            return False
        return hmac.compare_digest(sig, _sign(payload, secret))
    except Exception:
        return False


def require_ui_auth(req: Request) -> None:
    """
    UI dependency: allow request if valid cookie, otherwise redirect to /login.
    """
    secret = os.getenv("TAKS_UI_SECRET", "")
    tok = req.cookies.get("taks_auth")
    if secret and tok and verify_token(tok, secret):
        return None
    raise HTTPException(status_code=302, headers={"Location": "/login"})


def _parse_basic_auth(req: Request) -> Optional[Tuple[str, str]]:
    h = req.headers.get("authorization") or req.headers.get("Authorization")
    if not h:
        return None
    if not h.lower().startswith("basic "):
        return None
    b64 = h.split(" ", 1)[1].strip()
    try:
        raw = base64.b64decode(b64).decode("utf-8", errors="strict")
    except Exception:
        return None
    if ":" not in raw:
        return None
    user, pw = raw.split(":", 1)
    return user, pw


def verify_basic(req: Request) -> bool:
    """
    Headless auth for API: Authorization: Basic base64(user:pass)

    Defaults:
      user = orchestrator
      pass = TAKS_UI_PASSWORD (plaintext OK for now)
    """
    creds = _parse_basic_auth(req)
    if not creds:
        return False

    user, pw = creds
    want_user = (os.getenv("TAKS_UI_USER") or "orchestrator").strip()
    want_pw = (os.getenv("TAKS_UI_PASSWORD") or "").strip()
    if not want_pw:
        return False

    return hmac.compare_digest(user, want_user) and hmac.compare_digest(pw, want_pw)


def verify_cookie(req: Request) -> bool:
    secret = os.getenv("TAKS_UI_SECRET", "")
    tok = req.cookies.get("taks_auth")
    return bool(secret and tok and verify_token(tok, secret))
