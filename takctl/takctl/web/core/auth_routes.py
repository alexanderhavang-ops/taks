from __future__ import annotations

import hmac
import json
import os
import time
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from takctl.services.marti_auth import check_selected_user_store

RUNTIME_DIR = Path("/opt/tak/tools/takctl")
SECRET_FILE = RUNTIME_DIR / "secrets" / "session.key"
COOKIE_NAME = "takctl_session"
SESSION_TTL = 8 * 3600


def _load_secret() -> bytes:
    if SECRET_FILE.exists():
        return SECRET_FILE.read_bytes()
    SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
    key = os.urandom(32)
    SECRET_FILE.write_bytes(key)
    os.chmod(SECRET_FILE, 0o600)
    return key


_SECRET = _load_secret()


def _sign(payload: dict) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    sig = hmac.new(_SECRET, raw, "sha256").hexdigest()
    return raw.decode() + "." + sig


def _unsign(token: str) -> Optional[dict]:
    try:
        raw, sig = token.rsplit(".", 1)
        expect = hmac.new(_SECRET, raw.encode(), "sha256").hexdigest()
        if not hmac.compare_digest(sig, expect):
            return None
        return json.loads(raw)
    except Exception:
        return None


def get_session(req: Request) -> Optional[dict]:
    token = req.cookies.get(COOKIE_NAME)
    if not token:
        return None
    sess = _unsign(token)
    if not sess:
        return None
    exp = sess.get("exp", 0)
    if not isinstance(exp, (int, float)) or time.time() > float(exp):
        return None
    return sess


def mount_auth_routes(app: FastAPI) -> None:
    @app.get("/api/whoami")
    async def whoami(req: Request):
        sess = get_session(req)
        if not sess:
            return JSONResponse({"authenticated": False})
        return JSONResponse({"authenticated": True, "user": {"username": sess.get("u", "")}})

    @app.get("/api/logout")
    async def logout():
        resp = JSONResponse({"ok": True})
        resp.delete_cookie(COOKIE_NAME, path="/")
        return resp

    @app.get("/api/login")
    async def login_get():
        raise HTTPException(status_code=405, detail="Use POST /api/login")

    @app.post("/api/login")
    async def login(req: Request):
        body = await req.json()
        username = str(body.get("username", "")).strip()
        password = str(body.get("password", ""))

        if not username or not password:
            raise HTTPException(status_code=400, detail="username and password required")

        res = check_selected_user_store(username, password)
        if not res.ok:
            raise HTTPException(status_code=401, detail=f"Invalid credentials ({(res.error or '')[:160]})")

        sess = {"u": username, "exp": int(time.time() + SESSION_TTL)}
        token = _sign(sess)

        resp = JSONResponse({"ok": True, "user": {"username": username}})
        resp.set_cookie(
            COOKIE_NAME,
            token,
            httponly=True,
            secure=True,
            samesite="lax",
            path="/",
            max_age=SESSION_TTL,
        )
        return resp
