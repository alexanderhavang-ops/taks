from __future__ import annotations
from takctl.web.subsystems import load_subsystems, get_subsystems_status
from takctl.api.onboarding import router as onboarding_router
from takctl.api.onboarding_packages import router as onboarding_packages_router
from takctl.api.onboarding_cards_json import router as onboarding_cards_json_router
from takctl.api.onboarding_identity import router as onboarding_identity_router
from takctl.api.onboarding_policies import router as onboarding_policies_router

from takctl.api.onboarding_cards import router as onboarding_cards_router

import hmac
import json
import os
import time
import traceback
import uuid
from datetime import datetime, timezone
import html as _html
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.responses import JSONResponse, HTMLResponse, Response, FileResponse
from fastapi.staticfiles import StaticFiles

from takctl.api.health import router as health_router
from takctl.api.meta import router as meta_router
from takctl.services.marti_auth import check_userauthfile
from takctl.web.api import llm2_debug

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

# Runtime-owned brand metadata (uploader/orchestrator writes here)
BRAND_JSON = Path("/opt/tak/tools/takctl/assets/brand.json")


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except Exception:
        return False


def _safe_relpath(relpath: str) -> str:
    rp = str(relpath or "")
    if rp.startswith("/") or rp.startswith("..") or "/.." in rp or "\.." in rp:
        raise HTTPException(status_code=400, detail="bad asset path")
    return rp

def _safe_unit_fs(unit: str) -> str:
    # Keep it simple: allow [A-Za-z0-9._/-] only; block traversal.
    u = str(unit or "").strip()
    if not u:
        raise HTTPException(status_code=400, detail="bad unit")
    if u.startswith("/") or u.startswith("..") or "/.." in u or "\.." in u:
        raise HTTPException(status_code=400, detail="bad unit")
    # basic character whitelist
    for ch in u:
        o = ord(ch)
        ok = (
            (48 <= o <= 57) or (65 <= o <= 90) or (97 <= o <= 122) or
            ch in "._-/"
        )
        if not ok:
            raise HTTPException(status_code=400, detail="bad unit")
    return u

def _unit_root(unit_fs: str) -> Path:
    # unit-scoped upload root
    return USER_UPLOADS_DIR / unit_fs

def _unit_assets_dir(unit_fs: str) -> Path:
    # where splash.js expects unit logos: /u/<unit>/assets/logoN.ext
    return _unit_root(unit_fs) / "assets"



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
    return HTMLResponse((WEB_DIR / "splash.html").read_text(encoding="utf-8"))


@app.get("/splash.fragment.html")
async def splash_fragment_html():
    # Optional fragment used by splash.js in "standalone host" mode.
    # Explicit route (no wildcard) to avoid ever shadowing /api/*.
    return HTMLResponse((WEB_DIR / "splash.fragment.html").read_text(encoding="utf-8"))

@app.head("/splash.fragment.html")
async def splash_fragment_head():
    # Make curl -I and smoke tests happy (HEAD should behave like GET but without body).
    return Response(status_code=200)


@app.get("/splash.css")
async def splash_css():
    return Response((WEB_DIR / "splash.css").read_text(encoding="utf-8"), media_type="text/css")


@app.get("/splash.js")
async def splash_js():
    return Response((WEB_DIR / "splash.js").read_text(encoding="utf-8"), media_type="application/javascript")

# ---------------------------------------------------------------------
# Public unit branding (NO AUTH): used by splash.js
# Contract matches orchestrator:
#   GET /api/public/brand?unit=<unit_path>
# Returns brand.json if present; otherwise 404.
# On a node, 'unit' is optional; we serve the node-local brand.json regardless.
# ---------------------------------------------------------------------

@app.get("/api/public/brand")
async def public_brand(unit: str | None = None):
    """
    Public brand endpoint used by shared splash.js.

    Node behavior:
      - Prefer runtime override: /opt/tak/tools/takctl/assets/brand.json
      - Fallback to packaged default: <WEB_DIR>/assets/brand.json
      - IMPORTANT: on node, default login.role=false if missing (hide Role field)
    """
    import json

    candidates = [
        BRAND_JSON,
        (WEB_DIR / "assets" / "brand.json"),
    ]

    for bp in candidates:
        try:
            if bp.exists() and bp.is_file():
                data = json.loads(bp.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    data = {}

                # Default behavior on node: hide Role unless explicitly set
                login = data.get("login")
                if not isinstance(login, dict):
                    login = {}
                data["login"] = login
                if "role" not in login:
                    login["role"] = False

                return JSONResponse(data)
        except Exception:
            raise HTTPException(status_code=500, detail="Invalid brand.json")

    raise HTTPException(status_code=404, detail="Not Found")
# Orchestrator-compatible unit asset path:
#   /u/<unit_path>/assets/<relpath>
# On a node, map this to runtime user-uploads:
#   /opt/tak/tools/takctl/user-uploads/<unit_path>/assets/<relpath>
@app.get("/u/{unit_path:path}/assets/{relpath:path}")
async def public_unit_asset(unit_path: str, relpath: str):
    # basic traversal protection
    if relpath.startswith("/") or relpath.startswith("..") or "/.." in relpath:
        raise HTTPException(status_code=400, detail="bad asset path")
    if unit_path.startswith("/") or unit_path.startswith("..") or "/.." in unit_path:
        raise HTTPException(status_code=400, detail="bad unit path")

    req_path = (USER_UPLOADS_DIR / unit_path / "assets" / relpath)
    try:
        resolved = req_path.resolve(strict=True)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Not Found")

    uploads_root = USER_UPLOADS_DIR.resolve()
    if not _is_within(resolved, uploads_root):
        raise HTTPException(status_code=404, detail="Not Found")

    return FileResponse(str(resolved))


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

    # Authenticate against Marti UserAuthenticationFile.xml
    res = check_userauthfile(username, password)

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


# --- existing routers ---

# Preferred API namespace (NO legacy mounts):
app.include_router(health_router, prefix="/api")
app.include_router(meta_router, prefix="/api")
app.include_router(onboarding_router, prefix="/api")
app.include_router(onboarding_policies_router, prefix="/api")
app.include_router(onboarding_packages_router, prefix="/api")
app.include_router(onboarding_cards_json_router, prefix="/api")
app.include_router(onboarding_identity_router, prefix="/api")
app.include_router(onboarding_cards_router, prefix="/api")
app.include_router(llm2_debug.router)


# -----------------------------------------------------------------------------
# Debug helpers (safe: local/ops use only)
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# Debug: request-id + HTML error pages + last exception (admin-only)
# -----------------------------------------------------------------------------
_LAST_EXC = {
    "ts_utc": None,
    "request_id": None,
    "user": None,
    "method": None,
    "path": None,
    "traceback": None,
}

def _wants_html(req: Request) -> bool:
    # Basic "browser-ish" detection: Accept prefers HTML
    try:
        a = (req.headers.get("accept") or "").lower()
        return "text/html" in a
    except Exception:
        return False

def _debug_allowed(req: Request) -> bool:
    # Only show trace to authenticated users (takctl session cookie).
    return _get_session(req) is not None

def _taks_error_page(*, status: int, title: str, detail: str, rid: str, tb: str | None) -> HTMLResponse:
    # No f-strings here (avoid brace issues)
    esc = _html.escape
    hdr = esc(title or "Error")
    det = esc(detail or "")
    meta = "request_id=" + esc(rid or "") + "  status=" + str(int(status))
    tb_txt = tb or ""
    tb_html = "<pre>" + esc(tb_txt) + "</pre>" if tb_txt else "<div class=\"muted\">(no traceback)</div>"

    # Also show last exception (useful when you hit a 404/422 after a crash)
    le = _LAST_EXC
    last_meta = "ts_utc={ts}  request_id={rid}  user={u}".format(
        ts=esc(str(le.get("ts_utc") or "")),
        rid=esc(str(le.get("request_id") or "")),
        u=esc(str(le.get("user") or "")),
    )
    last_tb = le.get("traceback") or ""
    last_tb_html = "<pre>" + esc(last_tb) + "</pre>" if last_tb else "<div class=\"muted\">(none captured yet)</div>"

    html = """<!doctype html>
<html><head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{hdr}</title>
<style>
  body {{ font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; margin: 18px; background:#0b0d10; color:#e9eef5; }}
  .card {{ background:#10151b; border:1px solid #1f2a33; border-radius:14px; padding:14px; margin: 12px 0; }}
  .muted {{ color:#9fb0c0; font-size: 12px; }}
  h2 {{ margin: 0 0 6px 0; font-size: 18px; }}
  pre {{ white-space: pre-wrap; background: #07090c; color:#d7e1ee; padding: 12px; border-radius: 10px; overflow:auto; border:1px solid #1a222b; }}
  code {{ background:#07090c; border:1px solid #1a222b; border-radius:8px; padding:2px 6px; }}
  a {{ color:#7db7ff; text-decoration:none; }}
  a:hover {{ text-decoration:underline; }}
</style>
</head><body>
  <div class="card">
    <h2>{hdr}</h2>
    <div class="muted">{meta}</div>
    <div style="margin-top:10px">{det}</div>
  </div>

  <div class="card">
    <h2>Traceback</h2>
    <div class="muted">Shown only because you are authenticated.</div>
    {tb_html}
  </div>

  <div class="card">
    <h2>Last captured exception</h2>
    <div class="muted">{last_meta}</div>
    {last_tb_html}
    <div class="muted" style="margin-top:8px">
      JSON: <a href="/api/_debug/last_exception?format=json">/api/_debug/last_exception?format=json</a>
    </div>
  </div>
</body></html>
""".format(hdr=hdr, meta=meta, det=det, tb_html=tb_html, last_meta=last_meta, last_tb_html=last_tb_html)

    return HTMLResponse(html, status_code=int(status))

@app.middleware("http")
async def _taks_capture_last_exception(req: Request, call_next):
    rid = uuid.uuid4().hex[:12]
    # make request id available to handlers
    try:
        req.state.taks_request_id = rid
    except Exception:
        pass

    try:
        resp = await call_next(req)
        try:
            resp.headers["X-TAKS-Request-Id"] = rid
        except Exception:
            pass
        return resp
    except Exception:
        sess = _get_session(req)
        _LAST_EXC.update({
            "ts_utc": datetime.now(timezone.utc).isoformat(),
            "request_id": rid,
            "user": (sess or {}).get("u") if sess else None,
            "method": getattr(req, "method", None),
            "path": str(getattr(req, "url", "")),
            "traceback": traceback.format_exc(),
        })
        raise

@app.get("/api/_debug/last_exception", include_in_schema=False)
def _debug_last_exception(req: Request):
    sess = _get_session(req)
    if not sess:
        raise HTTPException(status_code=401, detail="not authenticated")
    fmt = (req.query_params.get("format") or "").strip().lower()
    if fmt == "json":
        return JSONResponse(_LAST_EXC)
    tb = _LAST_EXC.get("traceback") or "(no exception captured yet)"
    meta = "ts_utc={ts}  request_id={rid}  user={u}".format(
        ts=str(_LAST_EXC.get("ts_utc") or ""),
        rid=str(_LAST_EXC.get("request_id") or ""),
        u=str(_LAST_EXC.get("user") or ""),
    )
    html = "<!doctype html><html><head><meta charset=\"utf-8\"/><title>last_exception</title></head><body>" \
           "<div>" + _html.escape(meta) + "</div><pre>" + _html.escape(tb) + "</pre></body></html>"
    return HTMLResponse(html)

@app.get("/api/onboarding/cards/{token}/_debug/last_exception", include_in_schema=False)
def _public_card_last_exception(token: str, req: Request):
    """
    Public, token-scoped debug view.

    NO AUTH, but only reveals last exception if it occurred under the same
    /api/onboarding/cards/{token} namespace.
    """
    tok = (token or "").strip()
    if not tok:
        raise HTTPException(status_code=404, detail="Not Found")

    last_path = str(_LAST_EXC.get("path") or "")
    want = "/api/onboarding/cards/" + tok
    if want not in last_path:
        raise HTTPException(status_code=404, detail="Not Found")

    fmt = (req.query_params.get("format") or "").strip().lower()
    if fmt == "json":
        return JSONResponse(_LAST_EXC)

    tb = str(_LAST_EXC.get("traceback") or "")
    meta = (
        "ts_utc=" + str(_LAST_EXC.get("ts_utc") or "") +
        "  request_id=" + str(_LAST_EXC.get("request_id") or "") +
        "  user=" + str(_LAST_EXC.get("user") or "") +
        "  method=" + str(_LAST_EXC.get("method") or "") +
        "  path=" + last_path
    )

    html = (
        "<!doctype html><html><head><meta charset=\"utf-8\"/>"
        "<title>card last_exception</title></head><body>"
        "<div style=\"font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;\">"
        "<div>" + _html.escape(meta) + "</div>"
        "<pre style=\"white-space: pre-wrap;\">" + _html.escape(tb) + "</pre>"
        "</div></body></html>"
    )
    resp = HTMLResponse(html)
    try:
        resp.headers["X-TAKS-Request-Id"] = str(_LAST_EXC.get("request_id") or "")
    except Exception:
        pass
    return resp

# ---- Exception handlers that render HTML for browsers (only if authenticated) ----

@app.exception_handler(RequestValidationError)
async def _taks_handle_validation(req: Request, exc: RequestValidationError):
    rid = getattr(getattr(req, "state", None), "taks_request_id", "") or ""
    if _wants_html(req) and _debug_allowed(req):
        return _taks_error_page(status=422, title="422 Validation error", detail=str(exc), rid=rid, tb=None)
    return JSONResponse({"detail": exc.errors(), "request_id": rid}, status_code=422)

@app.exception_handler(StarletteHTTPException)
async def _taks_handle_starlette_http(req: Request, exc: StarletteHTTPException):
    rid = getattr(getattr(req, "state", None), "taks_request_id", "") or ""
    if _wants_html(req) and _debug_allowed(req):
        return _taks_error_page(status=int(exc.status_code), title=str(exc.status_code) + " HTTP error", detail=str(exc.detail), rid=rid, tb=None)
    return JSONResponse({"detail": exc.detail, "request_id": rid}, status_code=int(exc.status_code))

@app.exception_handler(HTTPException)
async def _taks_handle_fastapi_http(req: Request, exc: HTTPException):
    rid = getattr(getattr(req, "state", None), "taks_request_id", "") or ""
    if _wants_html(req) and _debug_allowed(req):
        return _taks_error_page(status=int(exc.status_code), title=str(exc.status_code) + " HTTP error", detail=str(exc.detail), rid=rid, tb=None)
    return JSONResponse({"detail": exc.detail, "request_id": rid}, status_code=int(exc.status_code))

@app.exception_handler(Exception)
async def _taks_handle_uncaught(req: Request, exc: Exception):
    rid = getattr(getattr(req, "state", None), "taks_request_id", "") or ""
    # middleware already captured traceback in _LAST_EXC, but we also render it here
    tb = traceback.format_exc()
    if _wants_html(req) and _debug_allowed(req):
        return _taks_error_page(status=500, title="500 Internal Server Error", detail=str(exc), rid=rid, tb=tb)
    return JSONResponse({"detail": "Internal Server Error", "request_id": rid}, status_code=500)



@app.exception_handler(Exception)
async def _taks_unhandled_exception(req: Request, exc: Exception):
    # Only render rich HTML trace for public soldier-card paths.
    # Everything else stays minimal (JSON), and the detailed trace remains in /api/_debug/last_exception (auth).
    try:
        path = str(getattr(req.url, "path", "") or "")
    except Exception:
        path = ""
    rid = ""
    try:
        rid = str(getattr(getattr(req, "state", None), "taks_request_id", "") or "")
    except Exception:
        rid = ""

    if path.startswith("/api/onboarding/cards/"):
        tb = traceback.format_exc()
        return _taks_error_page(
            status=500,
            title="Soldier Card Error",
            detail="Unhandled exception while rendering soldier card.",
            rid=rid,
            tb=tb,
        )

    # Default: keep it simple (don’t leak tracebacks on random endpoints)
    return JSONResponse({"detail": "internal server error", "request_id": rid}, status_code=500)

@app.get("/api/_debug/routes", include_in_schema=False)
def _debug_routes():
    out = []
    for r in app.router.routes:
        try:
            methods = sorted(list(getattr(r, "methods", []) or []))
            path = getattr(r, "path", None)
            name = getattr(r, "name", None)
            if path:
                out.append({"path": path, "methods": methods, "name": name})
        except Exception:
            continue
    return {"count": len(out), "routes": out}

