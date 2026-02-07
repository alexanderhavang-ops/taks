from __future__ import annotations

import base64
import hmac
import os
import time
from hashlib import sha256
from typing import Optional, Tuple


def _b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64u_dec(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode((s + pad).encode("ascii"))


<<<<<<< HEAD
def make_token(user: str, secret: str, ttl_seconds: int = 12 * 3600) -> str:
    """
    Simple signed token for cookie auth:
      payload: user|exp
      token: base64url(payload_bytes).sig
      sig: base64url(HMAC-SHA256(payload, secret))
=======
# ---------------------------------------------------------------------------
# Cookie auth (UI)
# ---------------------------------------------------------------------------

def make_token(user: str, secret: str, ttl_seconds: int = 12 * 3600) -> str:
    """
    Signed cookie token:
      payload = "user|exp"
      token   = base64url(payload) + "." + base64url(HMAC(payload, secret))
>>>>>>> 39e1394 (orchestrator: fix auth imports, headless basic auth, installer env load, LE preflight)
    """
    exp = int(time.time()) + int(ttl_seconds)
    payload = f"{user}|{exp}".encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), payload, sha256).digest()
    return f"{_b64u(payload)}.{_b64u(sig)}"


def verify_token(token: str, secret: str) -> bool:
    try:
        payload_b64, sig_b64 = token.split(".", 1)
        payload = _b64u_dec(payload_b64)
        sig = _b64u_dec(sig_b64)

        expected = hmac.new(secret.encode("utf-8"), payload, sha256).digest()
        if not hmac.compare_digest(sig, expected):
            return False

        user, exp_s = payload.decode("utf-8").split("|", 1)
<<<<<<< HEAD
        exp = int(exp_s)
        if not user:
            return False
        return time.time() <= exp
=======
        if not user:
            return False

        return time.time() <= int(exp_s)
>>>>>>> 39e1394 (orchestrator: fix auth imports, headless basic auth, installer env load, LE preflight)
    except Exception:
        return False


<<<<<<< HEAD
=======
# ---------------------------------------------------------------------------
# Basic auth (headless / cloud-init / curl)
# ---------------------------------------------------------------------------

>>>>>>> 39e1394 (orchestrator: fix auth imports, headless basic auth, installer env load, LE preflight)
def _parse_basic_auth(auth_header: Optional[str]) -> Optional[Tuple[str, str]]:
    if not auth_header:
        return None
    if not auth_header.lower().startswith("basic "):
        return None
<<<<<<< HEAD
    b64 = auth_header.split(" ", 1)[1].strip()
    try:
        raw = base64.b64decode(b64).decode("utf-8")
        if ":" not in raw:
            return None
        user, pw = raw.split(":", 1)
        return user, pw
=======
    try:
        raw = base64.b64decode(auth_header.split(" ", 1)[1]).decode("utf-8")
        if ":" not in raw:
            return None
        return raw.split(":", 1)
>>>>>>> 39e1394 (orchestrator: fix auth imports, headless basic auth, installer env load, LE preflight)
    except Exception:
        return None


def verify_basic_auth(auth_header: Optional[str]) -> bool:
    """
<<<<<<< HEAD
    Headless auth: Authorization: Basic base64(user:pass)

    For now:
      - user is fixed: TAKS_API_USER (default: "orchestrator")
      - password uses TAKS_API_PASSWORD if set, else falls back to TAKS_UI_PASSWORD
=======
    Headless auth via:
      Authorization: Basic base64(user:password)

    Defaults:
      user     = TAKS_API_USER     (default: "orchestrator")
      password = TAKS_API_PASSWORD or TAKS_UI_PASSWORD
>>>>>>> 39e1394 (orchestrator: fix auth imports, headless basic auth, installer env load, LE preflight)
    """
    parsed = _parse_basic_auth(auth_header)
    if not parsed:
        return False
<<<<<<< HEAD
    user, pw = parsed

    want_user = (os.getenv("TAKS_API_USER") or "orchestrator").strip()
    want_pw = os.getenv("TAKS_API_PASSWORD") or os.getenv("TAKS_UI_PASSWORD") or ""
    if not want_pw:
        return False

    return hmac.compare_digest(user, want_user) and hmac.compare_digest(pw, want_pw)
=======

    user, pw = parsed
    want_user = (os.getenv("TAKS_API_USER") or "orchestrator").strip()
    want_pw = os.getenv("TAKS_API_PASSWORD") or os.getenv("TAKS_UI_PASSWORD") or ""

    if not want_pw:
        return False

    return (
        hmac.compare_digest(user, want_user)
        and hmac.compare_digest(pw, want_pw)
    )
>>>>>>> 39e1394 (orchestrator: fix auth imports, headless basic auth, installer env load, LE preflight)

