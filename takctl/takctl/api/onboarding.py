from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from takctl.onboarding.onboarding_db import maybe_db
from takctl.onboarding.service_builder import build_service

router = APIRouter(tags=["onboarding"])

# -----------------------------------------------------------------------------
# Legacy compatibility shim:
# Some modules (e.g. onboarding_packages) historically imported _build_service
# from takctl.api.onboarding. Keep it as a thin wrapper.
# -----------------------------------------------------------------------------
def _build_service():
    return build_service()



@router.get("/onboarding/status")
def onboarding_status(
    unknown_limit: int = Query(50, ge=0, le=500),
    recent_minutes: int = Query(120, ge=1, le=24 * 60),
):
    svc = build_service()
    db, db_err, db_source, db_target = maybe_db()

    out = svc.status(
        db=db,
        unknown_limit=int(unknown_limit),
        recent_minutes=int(recent_minutes),
    )

    out.setdefault("meta", {})
    out["meta"]["db_attached"] = db is not None
    out["meta"]["db_source"] = db_source
    out["meta"]["db_target"] = db_target
    if db is None and db_err:
        out["meta"]["db_error"] = db_err

    return JSONResponse(out)
