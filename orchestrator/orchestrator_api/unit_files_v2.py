from __future__ import annotations

from pathlib import Path
from typing import Dict, Any, List

from fastapi import APIRouter, HTTPException, Request, UploadFile, File
from fastapi.responses import JSONResponse, FileResponse

from orchestrator_core.config import load_orch_config, load_secrets_config
from orchestrator_core.units_state import list_units

from .auth import verify_token

router = APIRouter(prefix="/api/v2/units")

ALLOWED_SUBTREES = ("packages", "branding", "users", "plugins", "maps", "missions", "misc")


def _state_dir() -> Path:
    cfg = load_orch_config()
    return Path(cfg.paths.state_dir)


def _is_authed(req: Request) -> bool:
    secret = load_secrets_config().auth.session_secret.strip()
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


def _parent_map() -> Dict[str, str]:
    out: Dict[str, str] = {}
    for row in list_units():
        up = str(row.get("unit_path") or "").strip()
        pp = str(row.get("parent_path") or "").strip()
        if up:
            out[up] = pp
    return out


def _inheritance_chain(unit_id: str) -> List[str]:
    pm = _parent_map()
    chain: List[str] = []
    seen = set()
    cur = unit_id
    while cur and cur not in seen:
        chain.append(cur)
        seen.add(cur)
        cur = str(pm.get(cur) or "").strip()
    return chain


def _local_file_path(unit_id: str, subtree: str, relname: str) -> Path:
    return _subtree_root(unit_id, subtree) / relname


def _find_effective_file(unit_id: str, subtree: str, relname: str) -> tuple[str, Path] | None:
    for src_unit in _inheritance_chain(unit_id):
        p = _local_file_path(src_unit, subtree, relname)
        if p.is_file():
            return src_unit, p
    return None


def _download_url(unit_id: str, subtree: str, relname: str) -> str:
    return (
        f"/api/v2/units/{unit_id}/files/download"
        f"?subtree={subtree}&name={relname}"
    )


def _delete_url(unit_id: str, subtree: str, relname: str) -> str:
    return (
        f"/api/v2/units/{unit_id}/files"
        f"?subtree={subtree}&name={relname}"
    )


@router.get("/{unit_path}/files")
def list_unit_files(unit_path: str, req: Request):
    if not _is_authed(req):
        raise HTTPException(status_code=401)

    unit_id = _validate_unit_id(unit_path)
    out: Dict[str, List[Dict[str, Any]]] = {}

    chain = _inheritance_chain(unit_id)

    for subtree in ALLOWED_SUBTREES:
        items: List[Dict[str, Any]] = []
        seen_relpaths = set()

        for src_unit in chain:
            root = _subtree_root(src_unit, subtree)
            for p in sorted(root.rglob("*")):
                if not p.is_file():
                    continue

                relname = str(p.relative_to(root))
                if relname in seen_relpaths:
                    continue
                seen_relpaths.add(relname)

                st = p.stat()
                inherited = src_unit != unit_id

                items.append({
                    "path": relname,
                    "bytes": st.st_size,
                    "kind": "inherited" if inherited else "local",
                    "inherited": inherited,
                    "source_unit": src_unit,
                    "download_url": _download_url(unit_id, subtree, relname),
                    "delete_url": None if inherited else _delete_url(unit_id, subtree, relname),
                })

        out[subtree] = items

    return JSONResponse({
        "unit": unit_id,
        "chain": chain,
        "subtrees": out,
    })


@router.get("/{unit_path}/files/download")
def download_unit_file(unit_path: str, subtree: str, name: str, req: Request):
    if not _is_authed(req):
        raise HTTPException(status_code=401)

    unit_id = _validate_unit_id(unit_path)
    subtree = _validate_subtree(subtree)
    relname = _validate_relname(name)

    found = _find_effective_file(unit_id, subtree, relname)
    if not found:
        raise HTTPException(status_code=404, detail="file not found")

    _src_unit, p = found
    return FileResponse(path=str(p), filename=p.name)


@router.delete("/{unit_path}/files")
def delete_unit_file(unit_path: str, subtree: str, name: str, req: Request):
    if not _is_authed(req):
        raise HTTPException(status_code=401)

    unit_id = _validate_unit_id(unit_path)
    subtree = _validate_subtree(subtree)
    relname = _validate_relname(name)

    p = _local_file_path(unit_id, subtree, relname)
    if not p.exists() or not p.is_file():
        raise HTTPException(status_code=404, detail="local file not found")

    p.unlink()

    parent = p.parent
    root = _subtree_root(unit_id, subtree)
    while parent != root and parent.exists():
        try:
            parent.rmdir()
        except OSError:
            break
        parent = parent.parent

    return JSONResponse({
        "ok": True,
        "unit": unit_id,
        "subtree": subtree,
        "path": relname,
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
