from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from .bundles_v2 import resolve_bundle_path
from orchestrator_core.bundle_download_auth import authorized

router = APIRouter()

@router.get("/bundles/{bundle_name}", include_in_schema=False)
def public_bundle_download(bundle_name: str, request: Request) -> FileResponse:
    """Short-lived per-launch header token; no cookies or interactive auth."""
    if not authorized(bundle_name, request.headers.get("x-taks-bootstrap", "")):
        raise HTTPException(status_code=403, detail="Bundle download denied")
    p: Path = resolve_bundle_path(bundle_name)
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"Bundle not found: {bundle_name}")
    return FileResponse(path=str(p), filename=p.name, media_type="application/gzip")
