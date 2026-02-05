from __future__ import annotations
from takctl.web.subsystems import load_subsystems, get_subsystems_status

import hmac
import json
import os
import time
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, HTMLResponse, Response, FileResponse
from fastapi.staticfiles import StaticFiles

from takctl.api.health import router as health_router
from takctl.api.meta import router as meta_router
from takctl.services.marti_auth import check_basic_auth

app = FastAPI(title="takctl-web")

# ------------------------------------------------------------
# Subsystem loader (best-effort): optional features must NOT
# prevent core webapp from starting.
# ------------------------------------------------------------
_SUBSYSTEMS = load_subsystems(app)

@app.get("/api/subsystems")
def api_subsystems():
    return get_subsystems_status()

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
    sess = _unsign(token)
    if not sess:
        return None
    exp = sess.get("exp", 0)
    if not isinstance(exp, (int, float)) or time.time() > float(exp):
        return None
    return sess


# Static UI from runtime web dir (nginx mounts /takctl/ -> backend /)
WEB_DIR = Path("/opt/tak/tools/takctl/web")

# Allow serving assets that are either:
# - real files inside WEB_DIR/assets
# - symlinks pointing into runtime user-uploads
USER_UPLOADS_DIR = Path("/opt/tak/tools/takctl/user-uploads")

def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except Exception:
        return False

@app.get("/assets/{relpath:path}")
async def assets(relpath: str):
    # Prevent absolute paths and obvious traversal
    if relpath.startswith("/") or relpath.startswith("..") or "/.." in relpath:
        raise HTTPException(status_code=400, detail="bad asset path")

    req_path = (WEB_DIR / "assets" / relpath)

    try:
        resolved = req_path.resolve(strict=True)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Not Found")

    # Permit either real assets dir or runtime user-uploads dir
    assets_root = (WEB_DIR / "assets").resolve()
    uploads_root = USER_UPLOADS_DIR.resolve()

    if not (_is_within(resolved, assets_root) or _is_within(resolved, uploads_root)):
        # Symlink escapes to somewhere else → blocked
        raise HTTPException(status_code=404, detail="Not Found")

    return FileResponse(str(resolved))
app.mount("/css", StaticFiles(directory=str(WEB_DIR / "css")), name="css")
app.mount("/components", StaticFiles(directory=str(WEB_DIR / "components")), name="components")
app.mount("/hooks", StaticFiles(directory=str(WEB_DIR / "hooks")), name="hooks")
app.mount("/vendor", StaticFiles(directory=str(WEB_DIR / "vendor")), name="vendor")


@app.get("/")
async def index():
    # Served by backend (nginx proxies /takctl/ -> backend /)
    return HTMLResponse((WEB_DIR / "index.html").read_text(encoding="utf-8"))


@app.get("/splash.html")
async def splash_html():
    # Fragment (no doctype on purpose)
    return HTMLResponse((WEB_DIR / "splash.html").read_text(encoding="utf-8"))


@app.get("/splash.css")
async def splash_css():
    return Response((WEB_DIR / "splash.css").read_text(encoding="utf-8"), media_type="text/css")


@app.get("/splash.js")
async def splash_js():
    return Response((WEB_DIR / "splash.js").read_text(encoding="utf-8"), media_type="application/javascript")


@app.get("/styles.css")
async def styles_css():
    return Response((WEB_DIR / "styles.css").read_text(encoding="utf-8"), media_type="text/css")


@app.get("/app.js")
async def app_js():
    return Response((WEB_DIR / "app.js").read_text(encoding="utf-8"), media_type="application/javascript")


# --- Session + auth endpoints ---

@app.get("/api/whoami")
async def whoami(req: Request):
    sess = _get_session(req)
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

    # Authenticate against Marti (username/password), avoid cert auth
    # NOTE: verify_tls=False for now (local loopback). We'll wire CA later.
    res = check_basic_auth(username, password, verify_tls=False)

    if not res.ok:
        # Keep error message minimal; no leakage
        raise HTTPException(status_code=401, detail="Invalid credentials")

    sess = {"u": username, "exp": int(time.time() + SESSION_TTL)}
    token = _sign(sess)

    resp = JSONResponse({"ok": True, "user": {"username": username}})
    resp.set_cookie(
        COOKIE_NAME,
        token,
        httponly=True,
        secure=True,     # you are on https via nginx
        samesite="lax",
        path="/",
        max_age=SESSION_TTL,
    )
    return resp


# --- existing routers ---

# --- existing routers ---
# Keep legacy paths:
app.include_router(health_router)
app.include_router(meta_router)

# Preferred API namespace:
app.include_router(health_router, prefix="/api")
app.include_router(meta_router, prefix="/api")
