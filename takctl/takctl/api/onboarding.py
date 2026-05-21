from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from takctl.onboarding.onboarding_db import maybe_db
from takctl.onboarding.service_builder import build_service
from takctl.services.openfire_presence import attach_openfire_to_status

router = APIRouter(tags=["onboarding"])


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

    attach_openfire_to_status(out)

    out["meta"] = {
        "db_attached": db is not None,
        "db_source": db_source,
        "db_target": db_target,
    }
    if db is None and db_err:
        out["meta"]["db_error"] = db_err

    return JSONResponse(
        jsonable_encoder(out),
        headers={"cache-control": "no-store, max-age=0", "pragma": "no-cache"},
    )
