from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from takctl.onboarding.onboarding_db import maybe_db
from takctl.onboarding.service_builder import build_service
from takctl.services.openfire_presence import openfire_for_username

router = APIRouter(tags=["onboarding"])


@router.get("/onboarding/users/{username}/card.json")
def onboarding_user_card_json(
    username: str,
    recent_minutes: int = Query(120, ge=1, le=24 * 60),
):
    svc = build_service()
    db, db_err, db_source, db_target = maybe_db()

    try:
        card = svc.user_card(
            username=username,
            db=db,
            recent_minutes=int(recent_minutes),
        )
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown user: {username}")

    openfire = openfire_for_username(username)
    if isinstance(card, dict):
        card["openfire"] = openfire
        card["xmpp"] = openfire

    out = {
        "card": card,
        "meta": {
            "db_attached": db is not None,
            "db_source": db_source,
            "db_target": db_target,
        },
    }
    if db is None and db_err:
        out["meta"]["db_error"] = db_err

    return JSONResponse(
        jsonable_encoder(out),
        headers={"cache-control": "no-store, max-age=0", "pragma": "no-cache"},
    )
