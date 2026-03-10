from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import APIRouter, Form, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, JSONResponse
from pydantic import BaseModel

from .auth import make_token, verify_token

router = APIRouter()

_TPL_DIR = Path(__file__).resolve().parent / "templates"
_STATIC_DIR = Path(__file__).resolve().parent / "static"

# Shared splash bundle installed by orchestrator-installer into runtime
_SHARED_ROOT = Path("/opt/tak-orch/orchestrator/orchestrator_api/static/shared/takctl")
_SHARED_CSS = _SHARED_ROOT / "css"
_SHARED_ASSETS = _SHARED_ROOT / "assets"


def _state_dir() -> Path:
  return Path(os.environ.get("TAKS_STATE_DIR") or "/opt/tak-orch/state")


def _html(name: str) -> str:
  return (_TPL_DIR / name).read_text(encoding="utf-8")


def _is_authed(req: Request) -> bool:
  secret = os.getenv("TAKS_UI_SECRET", "")
  tok = req.cookies.get("taks_auth")
  return bool(secret and tok and verify_token(tok, secret))


def _safe_join(base: Path, rel: str) -> Path:
  base_r = base.resolve()
  target = (base_r / rel).resolve()
  if base_r != target and base_r not in target.parents:
    raise HTTPException(status_code=404)
  return target


def _file_or_404(path: Path) -> FileResponse:
  if not path.exists() or not path.is_file():
    raise HTTPException(status_code=404)
  return FileResponse(str(path))


def _safe_unit_fs(unit_path: str) -> str:
  up = (unit_path or "").strip().strip("/")
  if not up:
    raise HTTPException(status_code=400, detail="Missing unit")
  if ".." in up.split("/"):
    raise HTTPException(status_code=400, detail="Invalid unit")
  return up


def _safe_relpath(relpath: str) -> str:
  rp = (relpath or "").strip().lstrip("/")
  if not rp:
    raise HTTPException(status_code=400, detail="Missing path")
  parts = [p for p in rp.split("/") if p]
  if any(p in (".", "..") for p in parts):
    raise HTTPException(status_code=400, detail="Invalid path")
  if any("\\" in p for p in parts):
    raise HTTPException(status_code=400, detail="Invalid path")
  return "/".join(parts)


def _unit_assets_dir(unit_path: str) -> Path:
  up = _safe_unit_fs(unit_path)
  d = _state_dir() / "units" / up / "assets"
  d.mkdir(parents=True, exist_ok=True)
  return d


# ---------------------------------------------------------------------
# Public splash + shared assets (NO AUTH)
# ---------------------------------------------------------------------

@router.get("/splash.html")
def splash_html():
  # Serve the shared takctl splash HTML as-is (keeps layout/CSS/JS expectations aligned)
  return _file_or_404(_safe_join(_SHARED_ROOT, "splash.html"))
@router.get("/splash.js")
def splash_js():
  return _file_or_404(_safe_join(_SHARED_ROOT, "splash.js"))


@router.get("/splash.css")
def splash_css():
  return _file_or_404(_safe_join(_SHARED_ROOT, "splash.css"))


@router.get("/splash.fragment.html")
def splash_fragment():
  return _file_or_404(_safe_join(_SHARED_ROOT, "splash.fragment.html"))


@router.get("/css/{path:path}")
def splash_css_dir(path: str):
  return _file_or_404(_safe_join(_SHARED_CSS, path))


@router.get("/assets/{path:path}")
def splash_assets_dir(path: str):
  return _file_or_404(_safe_join(_SHARED_ASSETS, path))


# ---------------------------------------------------------------------
# Public unit branding (NO AUTH): used by splash
# ---------------------------------------------------------------------

@router.get("/api/public/brand")
def public_brand(unit: str | None = None):
  """
  Returns brand.json for a unit if present, otherwise the shared brand.json.
  unit: unit_path like "forsvarsmakten/hemvarnet/46hvbat"
  """
  if unit:
    p = _unit_assets_dir(unit) / "brand.json"
    if p.exists() and p.is_file():
      try:
        return JSONResponse(json.loads(p.read_text(encoding="utf-8")))
      except Exception:
        pass

  shared = _safe_join(_SHARED_ASSETS, "brand.json")
  if shared.exists() and shared.is_file():
    try:
      return JSONResponse(json.loads(shared.read_text(encoding="utf-8")))
    except Exception:
      raise HTTPException(status_code=500, detail="Invalid shared brand.json")

  raise HTTPException(status_code=404)


@router.get("/u/{unit_path:path}/assets/{relpath:path}")
def public_unit_asset(unit_path: str, relpath: str):
  up = _safe_unit_fs(unit_path)
  rp = _safe_relpath(relpath)
  root = _unit_assets_dir(up)
  return _file_or_404(_safe_join(root, rp))


# ---------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------

@router.get("/api/whoami")
def whoami(req: Request):
  # Role is intentionally "future wiring": we store it now to keep UI fresh.
  role = req.cookies.get("taks_role") or ""
  return JSONResponse({"authenticated": _is_authed(req), "role": role})


@router.get("/login", response_class=HTMLResponse)
def login_get(req: Request):
  # Prefer the shared takctl splash login UI (single entry-point)
  if _is_authed(req):
    return RedirectResponse("/", status_code=302)
  return RedirectResponse("/splash.html", status_code=302)

@router.post("/login")
def login_post(password: str = Form(...), role: str = Form(default=""), username: str = Form(default="admin")):
  """
  Legacy form login (kept deterministic).
  """
  want = os.getenv("TAKS_UI_PASSWORD", "changeme")
  secret = os.getenv("TAKS_UI_SECRET", "")
  if password != want or not secret:
    return HTMLResponse("login failed\n", status_code=401)

  user = (username or "admin").strip() or "admin"
  tok = make_token(user, secret)

  resp = RedirectResponse("/", status_code=302)
  resp.set_cookie("taks_auth", tok, httponly=True, samesite="lax")
  # Role cookie is used later for RBAC decisions (server-side)
  resp.set_cookie("taks_role", (role or "").strip(), httponly=True, samesite="lax")
  return resp


class LoginReq(BaseModel):
  username: str = "admin"
  password: str = ""
  role: str = ""


@router.post("/api/login")
def api_login(req: LoginReq, request: Request):
  """
  Splash JS login endpoint:
    POST /api/login { username, password, role }
  Sets cookies and returns JSON {ok:true}.
  """
  want = (os.getenv("TAKS_UI_PASSWORD") or "changeme").strip()
  secret = (os.getenv("TAKS_UI_SECRET") or "").strip()
  if (req.password or "") != want or not secret:
    return JSONResponse({"ok": False, "error": "login failed"}, status_code=401)

  user = (req.username or "admin").strip() or "admin"
  role = (req.role or "").strip()

  tok = make_token(user, secret)
  resp = JSONResponse({"ok": True, "user": user, "role": role})
  resp.set_cookie("taks_auth", tok, httponly=True, samesite="lax")
  resp.set_cookie("taks_role", role, httponly=True, samesite="lax")
  return resp


@router.get("/logout")
def logout():
  resp = RedirectResponse("/login", status_code=302)
  resp.delete_cookie("taks_auth")
  resp.delete_cookie("taks_role")
  return resp


# ---------------------------------------------------------------------
# Gated UI
# ---------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
def ui_index(req: Request):
  if not _is_authed(req):
    return RedirectResponse("/login", status_code=302)
  return HTMLResponse(_html("index.html"))


@router.get("/static/{path:path}")
def static_files(path: str, req: Request):
  if not _is_authed(req):
    return RedirectResponse("/login", status_code=302)
  return _file_or_404(_safe_join(_STATIC_DIR, path))

# ---------------------------------------------------------------------
# Unit logo upload
# ---------------------------------------------------------------------

from fastapi import UploadFile, File

@router.post("/api/v2/units/{unit_path:path}/logo")
async def upload_unit_logo(unit_path: str, file: UploadFile = File(...), req: Request = None):
    if not _is_authed(req):
        raise HTTPException(status_code=401)

    up = _safe_unit_fs(unit_path)
    ext = (file.filename or "").split(".")[-1].lower()

    if ext not in ("svg", "png"):
        raise HTTPException(status_code=400, detail="Only svg or png allowed")

    d = _unit_assets_dir(up)

    # remove existing logos
    for f in d.glob("logo.*"):
        try:
            f.unlink()
        except Exception:
            pass

    dst = d / f"logo.{ext}"

    with dst.open("wb") as out:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)

    return {"ok": True, "unit": up, "file": dst.name}


# ---------------------------------------------------------------------
# Unit brand metadata save (slogan + symbol)
# ---------------------------------------------------------------------

class UnitBrandSave(BaseModel):
  slogan: str = ""
  symbol: str = ""

@router.post("/api/v2/units/{unit_path:path}/brand")
def save_unit_brand(unit_path: str, body: UnitBrandSave, req: Request):
  if not _is_authed(req):
    raise HTTPException(status_code=401)

  up = _safe_unit_fs(unit_path)
  d = _unit_assets_dir(up)
  bp = d / "brand.json"

  current = {}
  if bp.exists() and bp.is_file():
    try:
      current = json.loads(bp.read_text(encoding="utf-8"))
      if not isinstance(current, dict):
        current = {}
    except Exception:
      current = {}

  current["slogan"] = str(body.slogan or "").strip()
  current["symbol"] = str(body.symbol or "").strip()

  bp.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

  return JSONResponse({
    "ok": True,
    "unit": up,
    "brand": current,
  })

