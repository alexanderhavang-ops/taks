from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from takctl.services.zip_package_check import check_zip_url


router = APIRouter(prefix="/api/package-check", tags=["package-check"])


class ZipUrlCheckIn(BaseModel):
    zip_url: str = Field(..., min_length=1)
    expected_host: str = ""
    expected_user: str = ""
    expected_callsign: str = ""


@router.post("/zip-url")
def api_check_zip_url(body: ZipUrlCheckIn) -> dict[str, Any]:
    url = str(body.zip_url or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="zip_url is required")

    try:
        return check_zip_url(
            url,
            expected_host=str(body.expected_host or "").strip() or None,
            expected_user=str(body.expected_user or "").strip() or None,
            expected_callsign=str(body.expected_callsign or "").strip() or None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
