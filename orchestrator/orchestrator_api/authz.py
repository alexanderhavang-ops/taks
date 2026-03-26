from __future__ import annotations

from typing import Dict

from fastapi import HTTPException, Request

from orchestrator_core.config import load_secrets_config
from .auth import verify_basic_auth, verify_token


def require_auth(req: Request) -> Dict[str, str]:
    secrets = load_secrets_config()

    secret = secrets.auth.session_secret
    tok = req.cookies.get("taks_auth", "")

    if secret and tok and verify_token(tok, secret):
        return {"mode": "cookie"}

    auth_header = req.headers.get("authorization") or ""
    if verify_basic_auth(auth_header):
        return {"mode": "basic"}

    raise HTTPException(status_code=401, detail="Unauthorized")
