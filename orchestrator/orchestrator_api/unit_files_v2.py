from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Any, List

from fastapi import APIRouter, HTTPException, Request, UploadFile, File
from fastapi.responses import JSONResponse

from .auth import verify_token

router = APIRouter(prefix="/api/v2/units")

ALLOWED_SUBTREES = ("packages", "branding", "users", "plugins", "maps", "missions", "misc")


def _state_dir() -> Path:
    return Path(os.environ.get("TAKS_STATE_DIR") or "/opt/tak-orch/state")


def _is_authed(req: Request) -> bool:
    secret = (os.environ.get("TAKS_UI_SECRET") or "").strip()
    if not secret:
        return False
    tok = req.cookies.get("taks_auth") or ""
    return bool(tok and verify_token(tok, secret))


def _validate_unit_id(s: str, *, field: str = "unit_path") -> str:
    s = str(s or "").strip()
    if not s:
        raise HTTPException(status_code=400, detail=f"{field} is required")
    if "/" in s:
        raise HTTPException(status_code=400, detail=f"{field} must be a single id (no '/')")
    if s in (".", "..") or ".." in s:
        raise HTTPException(status_code=400, detail=f"{field} is invalid")
    return s


def _validate_subtree(s: str) -> str:
    s = str(s or "").strip()
    if s not in ALLOWED_SUBTREES:
        raise HTTPException(status_code=400, detail=f"invalid subtree: {s}")
    return s


def _validate_relname(name: str) -> str:
    name = str(name or "").strip().lstrip("/")
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    parts = [p for p in name.split("/") if p]
    if not parts:
        raise HTTPException(status_code=400, detail="name is required")
    if any(p in (".", "..") for p in parts):
        raise HTTPException(status_code=400, detail="invalid name")
    if any("\\" in p for p in parts):
        raise HTTPException(status_code=400, detail="invalid name")
    return "/".join(parts)


def _unit_root(unit_id: str) -> Path:
    return _state_dir() / "units" / unit_id


def _files_root(unit_id: str) -> Path:
    d = _unit_root(unit_id) / "files"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _subtree_root(unit_id: str, subtree: str) -> Path:
    d = _files_root(unit_id) / subtree
    d.mkdir(parents=True, exist_ok=True)
    return d


@router.get("/{unit_path}/files")
def list_unit_files(unit_path: str, req: Request):
    if not _is_authed(req):
        raise HTTPException(status_code=401)

    unit_id = _validate_unit_id(unit_path)
    out: Dict[str, List[Dict[str, Any]]] = {}

    for subtree in ALLOWED_SUBTREES:
        root = _subtree_root(unit_id, subtree)
        items: List[Dict[str, Any]] = []
        for p in sorted(root.rglob("*")):
            if not p.is_file():
                continue
            st = p.stat()
            items.append({
                "path": str(p.relative_to(root)),
                "bytes": st.st_size,
            })
        out[subtree] = items

    return JSONResponse({
        "unit": unit_id,
        "subtrees": out,
    })


@router.post("/{unit_path}/files/upload")
async def upload_unit_file(
    unit_path: str,
    subtree: str,
    name: str,
    file: UploadFile = File(...),
    req: Request = None,
):
    if not _is_authed(req):
        raise HTTPException(status_code=401)

    unit_id = _validate_unit_id(unit_path)
    subtree = _validate_subtree(subtree)
    relname = _validate_relname(name)

    root = _subtree_root(unit_id, subtree)
    dst = root / relname
    dst.parent.mkdir(parents=True, exist_ok=True)

    with dst.open("wb") as out:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)

    return JSONResponse({
        "ok": True,
        "unit": unit_id,
        "subtree": subtree,
        "path": relname,
        "file": dst.name,
    })
