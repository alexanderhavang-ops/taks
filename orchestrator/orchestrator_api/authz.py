from __future__ import annotations

import os
from typing import Dict

from fastapi import HTTPException, Request

from .auth import verify_basic_auth, verify_token


def require_auth(req: Request) -> Dict[str, str]:
    """
    Unified auth for v1 endpoints.

    Accepts:
      - UI cookie auth (taks_auth signed with TAKS_UI_SECRET)
      - OR HTTP Basic auth (TAKS_UI_USER / TAKS_UI_PASSWORD)

    This allows:
      - Browser UI to work via cookie
      - Headless nodes (cloud-init) to use BASIC auth
    """

    # --- Cookie auth (UI session) ---
    secret = os.environ.get("TAKS_UI_SECRET", "")
    tok = req.cookies.get("taks_auth", "")

    if secret and tok and verify_token(tok, secret):
        return {"mode": "cookie"}

    # --- Basic auth (node / headless client) ---
    auth_header = req.headers.get("authorization") or ""
    if verify_basic_auth(auth_header):
        return {"mode": "basic"}

    raise HTTPException(status_code=401, detail="Unauthorized")

