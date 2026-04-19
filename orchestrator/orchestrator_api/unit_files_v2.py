from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from starlette.background import BackgroundTask

from orchestrator_core.bundles import (
    _read_unit_chain,
    _select_takserver_deb,
    _subtree_source_dirs,
    _is_takserver_deb_path,
    default_bundle_dir,
    list_effective_branding_subtree_items,
    resolve_effective_branding_subtree_file,
    role_bundle_overlay_dir,
    unit_bundle_overlay_dir,
    unit_files_root,
)
from orchestrator_core.config import load_orch_config, load_secrets_config

from .auth import verify_token

router = APIRouter(prefix="/api/v2/units")

ALLOWED_SUBTREES = ("packages", "branding", "users", "plugins", "maps", "missions", "documents", "misc")
EFFECTIVE_ROLE = "tak-node"


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


def _files_root(unit_id: str) -> Path:
    d = unit_files_root(unit_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _subtree_root(unit_id: str, subtree: str) -> Path:
    d = _files_root(unit_id) / subtree
    d.mkdir(parents=True, exist_ok=True)
    return d


def _local_file_path(unit_id: str, subtree: str, relname: str) -> Path:
    return _subtree_root(unit_id, subtree) / relname


def _download_url(unit_id: str, subtree: str, relname: str) -> str:
    return f"/api/v2/units/{unit_id}/files/download?subtree={subtree}&name={relname}"


def _delete_url(unit_id: str, subtree: str, relname: str) -> str:
    return f"/api/v2/units/{unit_id}/files?subtree={subtree}&name={relname}"


def _same_path(a: Path, b: Path) -> bool:
    try:
        return a.resolve() == b.resolve()
    except Exception:
        return str(a) == str(b)


def _path_within(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except Exception:
        return False


def _should_skip_name(name: str) -> bool:
    s = str(name or "").strip()
    if not s:
        return True
    if s.startswith("."):
        return True
    if s.endswith(".template") or s.endswith(".example"):
        return True
    if s.endswith(".pyc") or s.endswith("~"):
        return True
    if ".bak." in s:
        return True
    return False


def _is_takserver_deb_name(name: str) -> bool:
    s = str(name or "").strip()
    return s.startswith("takserver_") and s.endswith("_all.deb")


def _source_meta(unit_id: str, subtree: str, src: Path) -> Dict[str, Any]:
    if _same_path(src, default_bundle_dir() / subtree):
        return {
            "kind": "default",
            "inherited": True,
            "source_unit": "default bundle",
            "deleteable": False,
        }

    if _same_path(src, role_bundle_overlay_dir(EFFECTIVE_ROLE) / subtree):
        return {
            "kind": "role",
            "inherited": True,
            "source_unit": f"role {EFFECTIVE_ROLE}",
            "deleteable": False,
        }

    if _same_path(src, unit_bundle_overlay_dir(unit_id) / subtree):
        return {
            "kind": "bundle_overlay",
            "inherited": False,
            "source_unit": unit_id,
            "deleteable": False,
        }

    for src_unit in _read_unit_chain(unit_id):
        cand = unit_files_root(src_unit) / subtree
        if _same_path(src, cand):
            inherited = src_unit != unit_id
            return {
                "kind": "inherited" if inherited else "local",
                "inherited": inherited,
                "source_unit": src_unit,
                "deleteable": not inherited,
            }

    return {
        "kind": "effective",
        "inherited": True,
        "source_unit": str(src),
        "deleteable": False,
    }


def _build_item(
    unit_id: str,
    subtree: str,
    relname: str,
    p: Path,
    src: Path,
    *,
    source_name: str = "",
    slot: str = "",
) -> Dict[str, Any]:
    st = p.stat()
    meta = _source_meta(unit_id, subtree, src)
    out: Dict[str, Any] = {
        "path": relname,
        "bytes": st.st_size,
        "kind": meta["kind"],
        "inherited": bool(meta["inherited"]),
        "source_unit": str(meta["source_unit"]),
        "resolved_path": str(p),
        "download_url": _download_url(unit_id, subtree, relname),
        "delete_url": _delete_url(unit_id, subtree, relname) if meta["deleteable"] else None,
    }
    if source_name:
        out["source_name"] = source_name
    if slot:
        out["slot"] = slot
    return out


def _public_item(unit_id: str, subtree: str, item: Dict[str, Any]) -> Dict[str, Any]:
    relname = str(item.get("path") or "")
    out: Dict[str, Any] = {
        "path": relname,
        "bytes": int(item.get("bytes") or 0),
        "kind": str(item.get("kind") or ""),
        "inherited": bool(item.get("inherited")),
        "source_unit": str(item.get("source_unit") or ""),
        "download_url": _download_url(unit_id, subtree, relname),
        "delete_url": _delete_url(unit_id, subtree, relname) if str(item.get("kind") or "") == "local" else None,
    }
    if item.get("source_name"):
        out["source_name"] = str(item.get("source_name") or "")
    if item.get("slot"):
        out["slot"] = str(item.get("slot") or "")
    return out


def _effective_generic_items(unit_id: str, subtree: str) -> List[Dict[str, Any]]:
    sources = _subtree_source_dirs(unit_id, EFFECTIVE_ROLE, subtree)
    effective: Dict[str, Dict[str, Any]] = {}

    for src in sources:
        if not src.exists() or not src.is_dir():
            continue

        for p in sorted(src.rglob("*")):
            if not p.is_file():
                continue
            if _should_skip_name(p.name):
                continue

            relname = str(p.relative_to(src))
            effective[relname] = _build_item(unit_id, subtree, relname, p, src)

    return [effective[k] for k in sorted(effective.keys())]


def _effective_packages_items(unit_id: str) -> List[Dict[str, Any]]:
    subtree = "packages"
    sources = _subtree_source_dirs(unit_id, EFFECTIVE_ROLE, subtree)
    effective: Dict[str, Dict[str, Any]] = {}

    for src in sources:
        if not src.exists() or not src.is_dir():
            continue

        for p in sorted(src.rglob("*")):
            if not p.is_file():
                continue
            if _should_skip_name(p.name):
                continue

            relname = str(p.relative_to(src))
            if _is_takserver_deb_path(Path(relname)):
                continue

            effective[relname] = _build_item(unit_id, subtree, relname, p, src)

    chosen_deb = _select_takserver_deb(sources)
    chosen_src = next((src for src in sources if _path_within(chosen_deb, src)), chosen_deb.parent)
    effective[chosen_deb.name] = _build_item(unit_id, subtree, chosen_deb.name, chosen_deb, chosen_src)

    return [effective[k] for k in sorted(effective.keys())]


def _effective_branding_items(unit_id: str) -> List[Dict[str, Any]]:
    items = list_effective_branding_subtree_items(unit_id)
    return [_public_item(unit_id, "branding", item) for item in items]


def _effective_items(unit_id: str, subtree: str) -> List[Dict[str, Any]]:
    if subtree == "branding":
        return _effective_branding_items(unit_id)
    if subtree == "packages":
        return _effective_packages_items(unit_id)
    return _effective_generic_items(unit_id, subtree)


def _resolve_effective_file(unit_id: str, subtree: str, relname: str) -> Optional[Dict[str, Any]]:
    if subtree == "branding":
        item = resolve_effective_branding_subtree_file(unit_id, relname)
        if item is None:
            return None
        row = dict(item)
        row["download_url"] = _download_url(unit_id, subtree, relname)
        row["delete_url"] = _delete_url(unit_id, subtree, relname) if str(row.get("kind") or "") == "local" else None
        return row

    sources = _subtree_source_dirs(unit_id, EFFECTIVE_ROLE, subtree)

    if subtree == "packages" and _is_takserver_deb_name(Path(relname).name):
        chosen_deb = _select_takserver_deb(sources)
        if chosen_deb.name == Path(relname).name:
            chosen_src = next((src for src in sources if _path_within(chosen_deb, src)), chosen_deb.parent)
            return _build_item(unit_id, subtree, relname, chosen_deb, chosen_src)

    found: Optional[Tuple[Path, Path]] = None
    for src in sources:
        p = src / relname
        if p.is_file() and not _should_skip_name(p.name):
            found = (src, p)

    if not found:
        return None

    src, p = found
    return _build_item(unit_id, subtree, relname, p, src)


@router.get("/{unit_path}/files")
def list_unit_files(unit_path: str, req: Request):
    if not _is_authed(req):
        raise HTTPException(status_code=401)

    unit_id = _validate_unit_id(unit_path)
    out: Dict[str, List[Dict[str, Any]]] = {}
    subtree_errors: Dict[str, str] = {}

    for subtree in ALLOWED_SUBTREES:
        try:
            items = _effective_items(unit_id, subtree)
            if subtree != "branding":
                items = [_public_item(unit_id, subtree, item) for item in items]
            out[subtree] = items
        except Exception as e:
            out[subtree] = []
            subtree_errors[subtree] = f"{type(e).__name__}: {e}"

    return JSONResponse(
        {
            "unit": unit_id,
            "chain": _read_unit_chain(unit_id),
            "effective_role": EFFECTIVE_ROLE,
            "subtrees": out,
            "subtree_errors": subtree_errors,
        }
    )


@router.get("/{unit_path}/files/download")
def download_unit_file(unit_path: str, subtree: str, name: str, req: Request):
    if not _is_authed(req):
        raise HTTPException(status_code=401)

    unit_id = _validate_unit_id(unit_path)
    subtree = _validate_subtree(subtree)
    relname = _validate_relname(name)

    try:
        found = _resolve_effective_file(unit_id, subtree, relname)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    if not found:
        raise HTTPException(status_code=404, detail="file not found")

    p = Path(str(found.get("resolved_path") or ""))
    if not p.exists() or not p.is_file():
        raise HTTPException(status_code=404, detail="file not found")

    cleanup_dir = str(found.get("cleanup_dir") or "").strip()
    background = BackgroundTask(shutil.rmtree, cleanup_dir, True) if cleanup_dir else None

    return FileResponse(path=str(p), filename=p.name, background=background)


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

    return JSONResponse(
        {
            "ok": True,
            "unit": unit_id,
            "subtree": subtree,
            "path": relname,
        }
    )


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

    if subtree == "branding":
        relname = str(relname).split("/")[-1]
        if not str(relname).lower().endswith(".png"):
            raise HTTPException(status_code=400, detail="branding subtree only accepts .png")
        root.mkdir(parents=True, exist_ok=True)
        for old in root.glob("*.png"):
            try:
                old.unlink()
            except Exception:
                pass

    dst = root / relname
    dst.parent.mkdir(parents=True, exist_ok=True)

    with dst.open("wb") as out:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)

    return JSONResponse(
        {
            "ok": True,
            "unit": unit_id,
            "subtree": subtree,
            "path": relname,
            "file": dst.name,
        }
    )
