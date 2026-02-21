from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from .bundles_v2 import resolve_bundle_path

router = APIRouter()

@router.get("/bundles/{bundle_name}", include_in_schema=False)
def public_bundle_download(bundle_name: str) -> FileResponse:
    """
    MAXIMUM BORING:
      - no auth
      - no cookies
      - direct file download
    """
    p: Path = resolve_bundle_path(bundle_name)
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"Bundle not found: {bundle_name}")
    return FileResponse(path=str(p), filename=p.name, media_type="application/gzip")
