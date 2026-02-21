# orchestrator/orchestrator_api/operator_auth.py
from __future__ import annotations

import base64
import os

from fastapi import HTTPException, Request

from .auth import verify_token


def _cookie_auth_ok(request: Request) -> bool:
    secret = (os.environ.get("TAKS_UI_SECRET") or "").strip()
    if not secret:
        return False
    tok = request.cookies.get("taks_auth") or ""
    return bool(tok and verify_token(tok, secret))


def _basic_auth_ok(request: Request) -> bool:
    want_user = (os.environ.get("TAKS_UI_USER") or "orchestrator").strip()
    want_pass = (os.environ.get("TAKS_UI_PASSWORD") or "changeme").strip()

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
    """
    Operator auth for UI/API actions.

    Accept either:
      - UI session cookie (taks_auth) signed with TAKS_UI_SECRET
      - HTTP Basic auth: TAKS_UI_USER / TAKS_UI_PASSWORD
    """
    if _cookie_auth_ok(request) or _basic_auth_ok(request):
        return
    raise HTTPException(status_code=401, detail="Unauthorized (session cookie or BASIC auth required)")
