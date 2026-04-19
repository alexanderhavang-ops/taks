from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

router = APIRouter(prefix="/files", tags=["file-browser"])


@dataclass(frozen=True)
class RootDef:
    key: str
    title: str
    candidates: Sequence[str]


ROOTS: List[RootDef] = [
    RootDef("documents", "Documents", ("/opt/tak/tools/takctl/data/library/documents",)),
    RootDef("plugins", "Plugins", ("/opt/tak/tools/takctl/plugins",)),
    RootDef("maps", "Maps", ("/opt/tak/maps", "/opt/tak/Maps")),
    RootDef("users", "Users", ("/opt/tak/users", "/opt/tak/Users")),
    RootDef("packages", "Packages", ("/opt/tak/packages", "/opt/tak/Packages", "/opt/tak/bootstrap/packages")),
    RootDef("branding", "Branding", ("/opt/tak/tools/takctl/web/assets/branding/node",)),
    RootDef("missions", "Missions", ("/opt/tak/missions", "/opt/tak/Missions")),
    RootDef("misc", "Misc", ("/opt/tak/misc", "/opt/tak/Misc")),
]

ROOT_MAP: Dict[str, RootDef] = {r.key: r for r in ROOTS}


def _iso_utc(ts: float) -> str:
    return datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _validate_root(root: str) -> str:
    key = str(root or "").strip().lower()
    if key not in ROOT_MAP:
        raise HTTPException(status_code=400, detail=f"invalid root: {root}")
    return key


def _clean_rel_path(path: str, *, allow_empty: bool) -> str:
    raw = str(path or "").strip().replace("\\", "/").strip("/")
    if not raw:
        if allow_empty:
            return ""
        raise HTTPException(status_code=400, detail="path is required")
    parts = [p for p in raw.split("/") if p]
    if not parts:
        if allow_empty:
            return ""
        raise HTTPException(status_code=400, detail="path is required")
    if any(p in (".", "..") for p in parts):
        raise HTTPException(status_code=400, detail="invalid path")
    return "/".join(parts)


def _validate_new_name(name: str) -> str:
    s = str(name or "").strip()
    if not s:
        raise HTTPException(status_code=400, detail="new_name is required")
    if "/" in s or "\\" in s:
        raise HTTPException(status_code=400, detail="new_name must be a single name")
    if s in (".", ".."):
        raise HTTPException(status_code=400, detail="invalid new_name")
    return s


def _pick_root_base(root_key: str) -> Path:
    root_def = ROOT_MAP[root_key]
    for cand in root_def.candidates:
        p = Path(cand)
        if p.exists() and p.is_dir():
            return p
    p = Path(root_def.candidates[0])
    p.mkdir(parents=True, exist_ok=True)
    return p


def _resolve(root_key: str, rel_path: str, *, allow_empty: bool) -> Tuple[Path, Path, str]:
    base = _pick_root_base(root_key).resolve()
    rel = _clean_rel_path(rel_path, allow_empty=allow_empty)
    target = base if not rel else (base / rel).resolve()
    try:
        target.relative_to(base)
    except Exception:
        raise HTTPException(status_code=400, detail="path escapes root")
    return base, target, rel


def _parent_rel(rel: str) -> str:
    rel = str(rel or "").strip("/")
    if not rel:
        return ""
    parts = rel.split("/")
    return "/".join(parts[:-1])


def _entry_from_child(base: Path, child: Path) -> dict | None:
    try:
        resolved = child.resolve()
        resolved.relative_to(base)
    except Exception:
        return None

    try:
        st = resolved.stat()
    except Exception:
        return None

    is_dir = resolved.is_dir()
    rel = str(child.relative_to(base)).replace(os.sep, "/")

    return {
        "name": child.name,
        "path": rel,
        "type": "dir" if is_dir else "file",
        "bytes": None if is_dir else int(st.st_size),
        "modified_ts": int(st.st_mtime),
        "modified_iso": _iso_utc(st.st_mtime),
        "downloadable": not is_dir,
        "renameable": True,
        "deleteable": True,
    }


def _sorted_children(target: Path) -> List[dict]:
    out: List[dict] = []
    for child in target.iterdir():
        row = _entry_from_child(target.resolve(), child)
        if row is None:
            continue
        out.append(row)
    out.sort(key=lambda x: (0 if x["type"] == "dir" else 1, str(x["name"]).lower()))
    return out


@router.get("/roots")
def list_roots():
    items = []
    for root_def in ROOTS:
        base = _pick_root_base(root_def.key)
        items.append(
            {
                "key": root_def.key,
                "title": root_def.title,
                "resolved_path": str(base),
            }
        )
    return {"ok": True, "roots": items}


@router.get("/list")
def list_dir(root: str, path: str = ""):
    root_key = _validate_root(root)
    base, target, rel = _resolve(root_key, path, allow_empty=True)

    if not target.exists():
        raise HTTPException(status_code=404, detail="directory not found")
    if not target.is_dir():
        raise HTTPException(status_code=400, detail="path is not a directory")

    return {
        "ok": True,
        "root": {
            "key": root_key,
            "title": ROOT_MAP[root_key].title,
            "resolved_path": str(base),
        },
        "path": rel,
        "parent_path": _parent_rel(rel),
        "entries": _sorted_children(target),
    }


@router.get("/download")
def download_item(root: str, path: str):
    root_key = _validate_root(root)
    _base, target, rel = _resolve(root_key, path, allow_empty=False)

    if not target.exists():
        raise HTTPException(status_code=404, detail="file not found")
    if not target.is_file():
        raise HTTPException(status_code=400, detail="download only supports files")

    return FileResponse(path=str(target), filename=Path(rel).name)


@router.delete("/item")
def delete_item(root: str, path: str):
    root_key = _validate_root(root)
    base, target, rel = _resolve(root_key, path, allow_empty=False)

    if not target.exists():
        raise HTTPException(status_code=404, detail="item not found")

    if target.is_dir():
        shutil.rmtree(target)
        kind = "dir"
    else:
        target.unlink()
        kind = "file"

    parent = Path(rel).parent
    while str(parent) not in ("", "."):
        cand = base / parent
        try:
            cand.rmdir()
        except OSError:
            break
        parent = parent.parent

    return {
        "ok": True,
        "root": root_key,
        "path": rel,
        "kind": kind,
        "deleted": True,
    }


@router.post("/rename")
def rename_item(root: str, path: str, new_name: str):
    root_key = _validate_root(root)
    base, target, rel = _resolve(root_key, path, allow_empty=False)
    new_name = _validate_new_name(new_name)

    if not target.exists():
        raise HTTPException(status_code=404, detail="item not found")

    src_parent = target.parent
    new_target = (src_parent / new_name).resolve()
    try:
        new_target.relative_to(base)
    except Exception:
        raise HTTPException(status_code=400, detail="rename escapes root")

    if target.resolve() == new_target:
        return {
            "ok": True,
            "root": root_key,
            "old_path": rel,
            "new_path": rel,
            "renamed": False,
        }

    if new_target.exists():
        raise HTTPException(status_code=409, detail="target already exists")

    target.rename(new_target)
    new_rel = str(new_target.relative_to(base)).replace(os.sep, "/")

    return {
        "ok": True,
        "root": root_key,
        "old_path": rel,
        "new_path": new_rel,
        "renamed": True,
    }


@router.post("/upload")
async def upload_item(root: str, path: str = "", file: UploadFile = File(...)):
    root_key = _validate_root(root)
    base, target_dir, rel = _resolve(root_key, path, allow_empty=True)

    if target_dir.exists() and not target_dir.is_dir():
        raise HTTPException(status_code=400, detail="path is not a directory")
    target_dir.mkdir(parents=True, exist_ok=True)

    filename = Path(str(file.filename or "")).name.strip()
    if not filename:
        raise HTTPException(status_code=400, detail="missing filename")

    dst = (target_dir / filename).resolve()
    try:
        dst.relative_to(base)
    except Exception:
        raise HTTPException(status_code=400, detail="upload escapes root")

    if dst.exists():
        raise HTTPException(status_code=409, detail="target already exists")

    fd, tmp_name = tempfile.mkstemp(prefix=".upload-", suffix=".tmp", dir=str(target_dir))
    os.close(fd)
    tmp_path = Path(tmp_name)

    try:
        with tmp_path.open("wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
        tmp_path.replace(dst)
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass

    saved_rel = str(dst.relative_to(base)).replace(os.sep, "/")

    return {
        "ok": True,
        "root": root_key,
        "dir": rel,
        "path": saved_rel,
        "filename": filename,
        "uploaded": True,
    }
