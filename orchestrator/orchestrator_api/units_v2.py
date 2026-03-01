# orchestrator/orchestrator_api/units_v2.py
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException, Request

from .operator_auth import require_operator

router = APIRouter(prefix="/api/v2/units")


# ----------------------------
# Paths + safety
# ----------------------------
def _state_dir() -> Path:
    return Path(os.environ.get("TAKS_STATE_DIR") or "/opt/tak-orch/state")


def _safe_unit_fs(unit_path: str) -> str:
    up = (unit_path or "").strip().strip("/")
    if not up:
        raise HTTPException(status_code=400, detail="Missing unit_path")
    if ".." in up.split("/"):
        raise HTTPException(status_code=400, detail="Invalid unit_path")
    return up


def _safe_relpath(relpath: str) -> str:
    rp = (relpath or "").strip().lstrip("/")
    if not rp:
        raise HTTPException(status_code=400, detail="Missing relpath")
    parts = [p for p in rp.split("/") if p]
    if any(p in (".", "..") for p in parts):
        raise HTTPException(status_code=400, detail="Invalid relpath")
    # Keep it boring: no backslashes
    if any("\\" in p for p in parts):
        raise HTTPException(status_code=400, detail="Invalid relpath")
    return "/".join(parts)


def unit_dir(unit_path: str) -> Path:
    up = _safe_unit_fs(unit_path)
    d = _state_dir() / "units" / up
    d.mkdir(parents=True, exist_ok=True)
    return d


def unit_meta_path(unit_path: str) -> Path:
    return unit_dir(unit_path) / "meta.json"


def unit_bundle_overlay_dir(unit_path: str) -> Path:
    d = unit_dir(unit_path) / "bundle"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _read_json(p: Path) -> Dict[str, Any]:
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON in {p}: {e}")


def _write_json(p: Path, obj: Dict[str, Any]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _list_overlay_files(root: Path) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not root.exists():
        return out
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = str(p.relative_to(root))
        st = p.stat()
        out.append(
            {
                "path": rel,
                "bytes": int(st.st_size),
                "mtime": int(st.st_mtime),
            }
        )
    return out


# ----------------------------
# API
# ----------------------------
@router.get("")
def units_list(request: Request) -> Dict[str, Any]:
    require_operator(request)

    # Source of truth: file-backed units (unit.json)
    from orchestrator_core.units_state import list_units as _list_units

    items = _list_units()
    return {"count": len(items), "items": items}

@router.get("/{unit_path}")
def unit_get(unit_path: str, request: Request) -> Dict[str, Any]:
    require_operator(request)
    up = _safe_unit_fs(unit_path)

    meta_p = unit_meta_path(up)
    meta = _read_json(meta_p)

    overlay_root = unit_bundle_overlay_dir(up)
    files = _list_overlay_files(overlay_root)

    return {
        "unit_path": up,
        "meta": meta,
        "bundle_overlay": {
            "root": str(overlay_root),
            "files": files,
        },
    }


@router.put("/{unit_path}/meta")
def unit_put_meta(unit_path: str, req: Dict[str, Any], request: Request) -> Dict[str, Any]:
    require_operator(request)
    up = _safe_unit_fs(unit_path)

    # Keep it flexible but JSON-object only
    if not isinstance(req, dict):
        raise HTTPException(status_code=400, detail="meta must be a JSON object")

    p = unit_meta_path(up)
    _write_json(p, req)

    return {"ok": True, "unit_path": up, "meta_path": str(p)}


@router.put("/{unit_path}/bundle/{relpath:path}")
def unit_put_overlay_file(unit_path: str, relpath: str, req: Dict[str, Any], request: Request) -> Dict[str, Any]:
    require_operator(request)
    up = _safe_unit_fs(unit_path)
    rp = _safe_relpath(relpath)

    """
    Body options:

      1) { "b64": "<base64 bytes>" }
      2) { "text": "..." }  (utf-8)
      3) { "json": {..} }   (written pretty as json)

    Optional:
      - "mode": 420  (octal 0644 as decimal) or 384 (0600), etc
    """
    if not isinstance(req, dict):
        raise HTTPException(status_code=400, detail="body must be a JSON object")

    data: Optional[bytes] = None
    if "b64" in req:
        try:
            data = base64.b64decode(str(req["b64"]), validate=True)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"invalid b64: {e}")
    elif "text" in req:
        data = str(req["text"]).encode("utf-8")
    elif "json" in req:
        if not isinstance(req["json"], (dict, list)):
            raise HTTPException(status_code=400, detail="json must be an object or array")
        data = (json.dumps(req["json"], indent=2, sort_keys=True) + "\n").encode("utf-8")
    else:
        raise HTTPException(status_code=400, detail="missing one of: b64, text, json")

    overlay_root = unit_bundle_overlay_dir(up)
    out = overlay_root / rp
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)

    mode = req.get("mode")
    if mode is not None:
        try:
            os.chmod(out, int(mode))
        except Exception:
            pass

    st = out.stat()
    return {
        "ok": True,
        "unit_path": up,
        "path": rp,
        "abs_path": str(out),
        "bytes": int(st.st_size),
        "mtime": int(st.st_mtime),
    }


@router.delete("/{unit_path}/bundle/{relpath:path}")
def unit_delete_overlay_file(unit_path: str, relpath: str, request: Request) -> Dict[str, Any]:
    require_operator(request)
    up = _safe_unit_fs(unit_path)
    rp = _safe_relpath(relpath)

    overlay_root = unit_bundle_overlay_dir(up)
    p = overlay_root / rp
    if not p.exists():
        raise HTTPException(status_code=404, detail="file not found")
    if not p.is_file():
        raise HTTPException(status_code=400, detail="not a file")

    p.unlink()
    return {"ok": True, "unit_path": up, "path": rp}

