from __future__ import annotations

import base64

from fastapi import HTTPException, Request

from orchestrator_core.config import load_secrets_config
from .auth import verify_token


def _cookie_auth_ok(request: Request) -> bool:
    secrets = load_secrets_config()
    secret = secrets.auth.session_secret
    tok = request.cookies.get("taks_auth") or ""
    return bool(tok and verify_token(tok, secret))


def _basic_auth_ok(request: Request) -> bool:
    secrets = load_secrets_config()
    want_user = secrets.auth.operator_user
    want_pass = secrets.auth.operator_password

    h = request.headers.get("authorization") or ""
    if not h.lower().startswith("basic "):
        return False

    b64 = h.split(None, 1)[1].strip()
    try:
        raw = base64.b64decode(b64).decode("utf-8", errors="strict")
    except Exception:
        return False

    if ":" not in raw:
        return False

    user, pw = raw.split(":", 1)
    return user == want_user and pw == want_pass


def require_operator(request: Request) -> None:
    if _cookie_auth_ok(request) or _basic_auth_ok(request):
        return
    raise HTTPException(status_code=401, detail="Unauthorized (session cookie or BASIC auth required)")
