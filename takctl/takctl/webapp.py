from __future__ import annotations

import hmac
import json
import os
import time
from pathlib import Path
from typing import Optional

import bcrypt
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from takctl.api.health import router as health_router
from takctl.api.meta import router as meta_router
from takctl.services.userauth_file import load_users

app = FastAPI(title="takctl-web")

# ---------------------------------------------------------------------------
# Session config (runtime-owned)
# ---------------------------------------------------------------------------

RUNTIME_DIR = Path("/opt/tak/tools/takctl")
SECRET_FILE = RUNTIME_DIR / "secrets" / "session.key"
COOKIE_NAME = "takctl_session"
SESSION_TTL = 8 * 3600  # 8 hours

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

def _get_session(req: Request) -> Optional[dict]:
    token = req.cookies.get(COOKIE_NAME)
    if not token:
        return None
    data = _unsign(token)
    if not data:
        return None
    if data.get("exp", 0) < time.time():
        return None
    return data

# ---------------------------------------------------------------------------
# Auth API
# ---------------------------------------------------------------------------

@app.post("/api/login")
async def login(req: Request):
    body = await req.json()
    username = body.get("username")
    password = body.get("password")

    if not username or not password:
        raise HTTPException(status_code=400, detail="Missing credentials")

    users = load_users()
    user = users.get(username)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not user.password_hash:
        raise HTTPException(status_code=401, detail="User has no password")

    if not bcrypt.checkpw(password.encode(), user.password_hash.encode()):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    payload = {
        "sub": username,
        "role": user.role,
        "groups": user.groups,
        "iat": int(time.time()),
        "exp": int(time.time()) + SESSION_TTL,
    }

    token = _sign(payload)

    resp = JSONResponse({"ok": True, "user": payload})
    resp.set_cookie(
        COOKIE_NAME,
        token,
        httponly=True,
        secure=False,   # nginx TLS terminates; backend sees http
        samesite="lax",
        max_age=SESSION_TTL,
        path="/",
    )
    return resp

@app.post("/api/logout")
async def logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(COOKIE_NAME, path="/")
    return resp

@app.get("/api/whoami")
async def whoami(req: Request):
    sess = _get_session(req)
    if not sess:
        return JSONResponse({"authenticated": False})
    return JSONResponse({"authenticated": True, "user": sess})

# ---------------------------------------------------------------------------
# API routers (unauthenticated for now)
# ---------------------------------------------------------------------------

app.include_router(health_router, prefix="/api")
app.include_router(health_router, prefix="/api/v1")
app.include_router(meta_router, prefix="/api")
app.include_router(meta_router, prefix="/api/v1")

# ---------------------------------------------------------------------------
# Static UI
# ---------------------------------------------------------------------------

WEB_DIR = Path(__file__).resolve().parents[1] / "web"
if WEB_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")

