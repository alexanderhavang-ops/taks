from __future__ import annotations

import hmac
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from takctl.services.orchestrator_backup import (
    create_backup,
    get_backup_artifact_path,
    get_backup_manifest,
)

router = APIRouter(prefix="/api/orchestrator", tags=["orchestrator"])


def _parse_simple_kv_text(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in str(text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip()
        if k:
            out[k] = v
    return out


def _secret_candidates() -> list[Path]:
    return [
        Path("/opt/tak/tools/takctl/secrets.d/orchestrator-node.conf"),
        Path("/etc/taks-bootstrap.d/secrets.d/orchestrator-node.conf"),
        Path("/opt/tak/tools/takctl/secrets.conf"),
    ]


def _read_local_orchestrator_secret() -> str:
    for p in _secret_candidates():
        if not p.exists() or not p.is_file():
            continue
        try:
            data = _parse_simple_kv_text(p.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue
        val = str(data.get("orchestrator_node_secret", "") or "").strip()
        if val:
            return val
    return ""


def _read_presented_secret(request: Request) -> str:
    auth = (request.headers.get("authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        tok = auth[7:].strip()
        if tok:
            return tok

    tok = (request.headers.get("x-taks-orchestrator-secret") or "").strip()
    if tok:
        return tok

    return ""


def require_orchestrator_secret(request: Request) -> None:
    want = _read_local_orchestrator_secret()
    if not want:
        raise HTTPException(status_code=503, detail="orchestrator secret not configured on node")

    got = _read_presented_secret(request)
    if not got:
        raise HTTPException(status_code=401, detail="missing orchestrator secret")

    if not hmac.compare_digest(got, want):
        raise HTTPException(status_code=401, detail="invalid orchestrator secret")


class BackupCreateIn(BaseModel):
    buckets: List[str] = Field(default_factory=list)


@router.get("/ping")
def orchestrator_ping(request: Request) -> Dict[str, object]:
    require_orchestrator_secret(request)
    return {
        "ok": True,
        "auth": "orchestrator_node_secret",
    }


@router.post("/backups")
def orchestrator_create_backup(request: Request, body: BackupCreateIn) -> Dict[str, Any]:
    require_orchestrator_secret(request)
    try:
        result = create_backup(body.buckets)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    backup_id = str(result.get("backup_id") or "").strip()
    return {
        "ok": True,
        "backup_id": backup_id,
        "manifest": result.get("manifest") or {},
        "size_bytes": int(result.get("size_bytes") or 0),
        "download_path": f"/api/orchestrator/backups/{backup_id}/artifact",
        "manifest_path": f"/api/orchestrator/backups/{backup_id}/manifest",
    }


@router.get("/backups/{backup_id}/manifest")
def orchestrator_backup_manifest(request: Request, backup_id: str) -> Dict[str, Any]:
    require_orchestrator_secret(request)
    try:
        return get_backup_manifest(backup_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/backups/{backup_id}/artifact")
def orchestrator_backup_artifact(request: Request, backup_id: str):
    require_orchestrator_secret(request)
    try:
        p = get_backup_artifact_path(backup_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return FileResponse(
        path=str(p),
        media_type="application/gzip",
        filename=f"{backup_id}.backup.tar.gz",
    )
