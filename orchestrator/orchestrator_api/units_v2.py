from __future__ import annotations

import json
import shutil
from orchestrator_core.config import load_orch_config
import time
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse


router = APIRouter(prefix="/api/v2/units")


def _validate_unit_id(s: str, *, field: str) -> str:
    s = str(s or "").strip().lower()
    if not s:
        raise HTTPException(status_code=400, detail=f"{field} is required")
    if "/" in s:
        raise HTTPException(status_code=400, detail=f"{field} must be a single id (no '/')")
    if s in (".", "..") or ".." in s:
        raise HTTPException(status_code=400, detail=f"{field} is invalid")
    return s


def _validate_parent_id(s: str) -> str:
    s = str(s or "").strip().lower()
    if not s:
        return ""
    return _validate_unit_id(s, field="parent_path")


def _state_dir() -> Path:
    cfg = load_orch_config()
    return Path(cfg.paths.state_dir)


def _units_root() -> Path:
    return _state_dir() / "units"


def _quarantine_root() -> Path:
    return _state_dir() / "quarantine" / "units"


def _unit_dir(unit_id: str) -> Path:
    return _units_root() / unit_id


def _unit_json_path(unit_id: str) -> Path:
    return _unit_dir(unit_id) / "unit.json"


def _now() -> int:
    return int(time.time())


def _read_json(p: Path) -> Dict[str, Any]:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read json: {p}: {e}")


def _write_json(p: Path, obj: Dict[str, Any]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(p)


def _normalize_unit_record(unit_id: str, j: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "unit_path": str(j.get("unit_path", unit_id) or unit_id).strip().lower(),
        "title": j.get("title", unit_id),
        "parent_path": str(j.get("parent_path", "") or "").strip().lower(),
        "created_ts": int(j.get("created_ts") or 0),
        "updated_ts": int(j.get("updated_ts") or 0),
        "meta": j.get("meta") or {},
        "overlay_files": int(j.get("overlay_files") or 0),
    }


def _list_units() -> List[Dict[str, Any]]:
    root = _units_root()
    if not root.exists():
        return []
    out: List[Dict[str, Any]] = []
    for d in sorted([x for x in root.iterdir() if x.is_dir()]):
        uj = d / "unit.json"
        if not uj.exists():
            continue
        j = _read_json(uj)
        out.append(_normalize_unit_record(d.name.lower(), j))
    return out


@router.get("")
def list_units() -> JSONResponse:
    items = _list_units()
    return JSONResponse({"count": len(items), "items": items})


@router.post("")
async def create_unit(req: Request) -> JSONResponse:
    body = await req.json()

    unit_id = _validate_unit_id(body.get("unit_path"), field="unit_path")
    title = str(body.get("title") or "").strip() or unit_id
    parent_id = _validate_parent_id(body.get("parent_path"))
    meta = body.get("meta") or {}

    uj = _unit_json_path(unit_id)
    if uj.exists():
        raise HTTPException(status_code=409, detail="unit already exists")

    now = _now()
    j = {
        "unit_path": unit_id,
        "title": title,
        "parent_path": parent_id,
        "created_ts": now,
        "updated_ts": now,
        "meta": meta,
        "overlay_files": 0,
    }
    _write_json(uj, j)
    return JSONResponse(_normalize_unit_record(unit_id, j))


@router.patch("/{unit_path}")
async def update_unit(unit_path: str, req: Request) -> JSONResponse:
    unit_id = _validate_unit_id(unit_path, field="unit_path")
    body = await req.json()

    uj = _unit_json_path(unit_id)
    if not uj.exists():
        raise HTTPException(status_code=404, detail="unit not found")

    j = _read_json(uj)

    if "title" in body:
        j["title"] = str(body.get("title") or "").strip()
    if "parent_path" in body:
        j["parent_path"] = _validate_parent_id(body.get("parent_path"))
    if "meta" in body:
        j["meta"] = body.get("meta") or {}

    j["unit_path"] = unit_id
    j["updated_ts"] = _now()

    _write_json(uj, j)
    return JSONResponse(_normalize_unit_record(unit_id, j))


@router.delete("/{unit_path}")
def delete_unit(unit_path: str) -> JSONResponse:
    unit_id = _validate_unit_id(unit_path, field="unit_path")
    d = _unit_dir(unit_id)
    if not d.exists():
        raise HTTPException(status_code=404, detail="unit not found")

    qroot = _quarantine_root()
    qroot.mkdir(parents=True, exist_ok=True)

    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    dest = qroot / f"{ts}__{unit_id}"
    if dest.exists():
        dest = qroot / f"{ts}__{unit_id}__{_now()}"

    try:
        shutil.move(str(d), str(dest))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to quarantine unit: {e}")

    return JSONResponse({"ok": True, "unit_path": unit_id, "quarantined_to": str(dest)})
