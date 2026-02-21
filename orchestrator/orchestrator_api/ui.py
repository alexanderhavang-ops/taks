from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Form, Request, Response, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse

from .auth import make_token, verify_token

router = APIRouter()

_TPL_DIR = Path(__file__).resolve().parent / "templates"
_STATIC_DIR = Path(__file__).resolve().parent / "static"


def _html(name: str) -> str:
    return (_TPL_DIR / name).read_text(encoding="utf-8")


def _is_authed(req: Request) -> bool:
    secret = os.getenv("TAKS_UI_SECRET", "")
    tok = req.cookies.get("taks_auth")
    return bool(secret and tok and verify_token(tok, secret))


@router.get("/login", response_class=HTMLResponse)
def login_get():
    return HTMLResponse(_html("login.html"))


@router.post("/login")
def login_post(password: str = Form(...)):
    want = os.getenv("TAKS_UI_PASSWORD", "changeme")
    secret = os.getenv("TAKS_UI_SECRET", "")
    if password != want or not secret:
        return HTMLResponse("login failed\n", status_code=401)

    tok = make_token("admin", secret)
    resp = RedirectResponse("/", status_code=302)
    resp.set_cookie("taks_auth", tok, httponly=True, samesite="lax")
    return resp


@router.get("/logout")
def logout():
    resp = RedirectResponse("/login", status_code=302)
    resp.delete_cookie("taks_auth")
    return resp


@router.head("/")
def ui_index_head(req: Request):
    if _is_authed(req):
        return Response(status_code=200)
    return RedirectResponse("/login", status_code=302)


@router.get("/", response_class=HTMLResponse)
def ui_index(req: Request):
    if not _is_authed(req):
        return RedirectResponse("/login", status_code=302)
    return HTMLResponse(_html("index.html"))


@router.get("/static/{path:path}")
def static_files(path: str, req: Request):
    """
    Serve small static assets (css/js/img) for the UI without needing Swagger/StaticFiles.
    Auth-gated: same cookie as the UI.
    """
    if not _is_authed(req):
        return RedirectResponse("/login", status_code=302)

    # Prevent path traversal
    base = _STATIC_DIR.resolve()
    target = (base / path).resolve()
    if base not in target.parents and target != base:
        raise HTTPException(status_code=404, detail="not found")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="not found")

    return FileResponse(str(target))

