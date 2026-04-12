from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from orchestrator_core.unit_bootstrap import (
    delete_local_file,
    effective_file_texts,
    list_effective_sources,
    list_local_files,
    local_file_path,
    local_file_texts,
    write_local_file,
)

from orchestrator_core.policy_caps import describe_unit_policy

from .api_v2 import require_operator

router = APIRouter(prefix="/api/v2/units")


def _validate_unit_id(s: str) -> str:
    s = str(s or "").strip()
    if not s:
        raise HTTPException(status_code=400, detail="unit_path is required")
    if "\\" in s or s in (".", "..") or ".." in s:
        raise HTTPException(status_code=400, detail="invalid unit_path")
    return s.strip("/")


def _validate_kind(kind: str) -> bool:
    k = str(kind or "").strip().lower()
    if k in ("config", "conf", "conf.d"):
        return False
    if k in ("secret", "secrets", "secrets.d"):
        return True
    raise HTTPException(status_code=400, detail=f"invalid kind: {kind}")


def _validate_scope(scope: str) -> str:
    s = str(scope or "").strip().lower() or "local"
    if s not in ("local", "effective"):
        raise HTTPException(status_code=400, detail=f"invalid scope: {scope}")
    return s


@router.get("/{unit_path}/bootstrap")
def get_unit_bootstrap(unit_path: str, request: Request) -> Dict[str, Any]:
    require_operator(request)
    unit_id = _validate_unit_id(unit_path)

    local_conf = local_file_texts(unit_id, secret=False)
    local_sec = local_file_texts(unit_id, secret=True)
    eff_conf = effective_file_texts(unit_id, secret=False)
    eff_sec = effective_file_texts(unit_id, secret=True)
    eff_conf_sources = list_effective_sources(unit_id, secret=False)
    eff_sec_sources = list_effective_sources(unit_id, secret=True)

    return {
        "ok": True,
        "unit": unit_id,
        "policy": describe_unit_policy(unit_id),
        "local": {
            "conf_d": local_conf,
            "secrets_d": local_sec,
        },
        "effective": {
            "conf_d": eff_conf,
            "secrets_d": eff_sec,
        },
        "effective_sources": {
            "conf_d": eff_conf_sources,
            "secrets_d": eff_sec_sources,
        },
    }


@router.get("/{unit_path}/bootstrap/files")
def list_unit_bootstrap_files(unit_path: str, request: Request) -> JSONResponse:
    require_operator(request)
    unit_id = _validate_unit_id(unit_path)

    def build(secret: bool) -> List[Dict[str, Any]]:
        local = list_local_files(unit_id, secret=secret)
        effective = effective_file_texts(unit_id, secret=secret)
        sources = list_effective_sources(unit_id, secret=secret)
        items: List[Dict[str, Any]] = []
        for name in sorted(set(local.keys()) | set(effective.keys())):
            items.append({
                "name": name,
                "kind": "secrets.d" if secret else "conf.d",
                "local": name in local,
                "effective": name in effective,
                "sources": sources.get(name, []),
                "bytes": len(effective.get(name, local.get(name).read_text(encoding='utf-8') if name in local else '')),
            })
        return items

    return JSONResponse({
        "ok": True,
        "unit": unit_id,
        "conf_d": build(secret=False),
        "secrets_d": build(secret=True),
    })


@router.get("/{unit_path}/bootstrap/file")
def get_unit_bootstrap_file(unit_path: str, kind: str, name: str, scope: str = "local", request: Request = None):
    require_operator(request)
    unit_id = _validate_unit_id(unit_path)
    secret = _validate_kind(kind)
    scope = _validate_scope(scope)

    if scope == "local":
        try:
            p = local_file_path(unit_id, secret=secret, name=name)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        if not p.exists() or not p.is_file():
            raise HTTPException(status_code=404, detail="local file not found")
        return PlainTextResponse(p.read_text(encoding="utf-8"))

    text_map = effective_file_texts(unit_id, secret=secret)
    if name not in text_map:
        raise HTTPException(status_code=404, detail="effective file not found")
    return PlainTextResponse(text_map[name])


@router.post("/{unit_path}/bootstrap/file")
async def save_unit_bootstrap_file(unit_path: str, kind: str, name: str, request: Request):
    require_operator(request)
    unit_id = _validate_unit_id(unit_path)
    secret = _validate_kind(kind)

    try:
        body = await request.json()
        content = str((body or {}).get("content") or "")
    except Exception:
        content = (await request.body()).decode("utf-8", errors="replace")

    try:
        p = write_local_file(unit_id, secret=secret, name=name, content=content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "ok": True,
        "unit": unit_id,
        "kind": "secrets.d" if secret else "conf.d",
        "name": name,
        "path": str(p),
    }


@router.delete("/{unit_path}/bootstrap/file")
def delete_unit_bootstrap_file(unit_path: str, kind: str, name: str, request: Request):
    require_operator(request)
    unit_id = _validate_unit_id(unit_path)
    secret = _validate_kind(kind)
    try:
        p = delete_local_file(unit_id, secret=secret, name=name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="local file not found")

    return {
        "ok": True,
        "unit": unit_id,
        "kind": "secrets.d" if secret else "conf.d",
        "name": name,
        "path": str(p),
    }
