from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from takctl.onboarding.onboarding_db import maybe_db
from takctl.onboarding.service_builder import build_service

router = APIRouter(tags=["onboarding"])


@router.get("/onboarding/users/{username}/card")
def onboarding_user_card(
    username: str,
    recent_minutes: int = Query(120, ge=1, le=24 * 60),
):
    """
    Single-user view model for the Web UI:
      - TAK user (from UserAuthenticationFile.xml)
      - onboarding store (filejson state)
      - correlated activity (from CoT DB), if available
      - meta: db attachment info
    """
    svc = build_service()
    db, db_err, db_source, db_target = maybe_db()

    try:
        card = svc.user_card(username=username, db=db, recent_minutes=int(recent_minutes))
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown user: {username}")

    out = {"card": card}
    out.setdefault("meta", {})
    out["meta"]["db_attached"] = db is not None
    out["meta"]["db_source"] = db_source
    out["meta"]["db_target"] = db_target
    if db is None and db_err:
        out["meta"]["db_error"] = db_err

    return JSONResponse(out)
