from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from takctl.onboarding.onboarding_db import maybe_db
from takctl.onboarding.service_builder import build_service

# selection.json (generate/submit) is part of the card model
from takctl.onboarding.selection import load_selection

router = APIRouter(tags=["onboarding"])


@router.get("/onboarding/users/{username}/card.json")
def onboarding_user_card_json(
    username: str,
    recent_minutes: int = Query(120, ge=1, le=24 * 60),
):
    """
    JSON view model for Web UI (no HTML):
      - TAK user (UserAuthenticationFile.xml)
      - taks_identity (optional)
      - selection (generate/submit)
      - onboarding store (filejson stage gates)
      - correlated CoT activity (DB), if available
      - meta: db attachment info
    """
    svc = build_service()
    db, db_err, db_source, db_target = maybe_db()

    try:
        card = svc.user_card(username=username, db=db, recent_minutes=int(recent_minutes))
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown user: {username}")

    # Attach selection (if present)
    try:
        sel = load_selection(username) or None
        if isinstance(card, dict):
            card["selection"] = sel
    except Exception:
        pass

    # -------------------------------------------------------------------------
    # authority / ownership hints (UI semantics; does not change stage gates)
    # -------------------------------------------------------------------------
    try:
        ident = (card.get("taks_identity") or {}) if isinstance(card, dict) else {}
        pw_known = bool(ident.get("password_known")) if isinstance(ident, dict) else False
        origin = ident.get("origin") if isinstance(ident, dict) else None
        if isinstance(card, dict):
            card["authority"] = {
                "tak_user": "marti_xml",
                "groups": {
                    "authoritative": "marti_xml",
                    "writable_by_taks": False,
                    "notes": "Groups are currently observed from UserAuthenticationFile.xml; TAKS does not write them yet.",
                },
                "password": {
                    "authoritative": ("taks" if pw_known else "marti_unknown"),
                    "known_to_taks": pw_known,
                },
                "identity_overlay": {
                    "present": bool(card.get("taks_identity")),
                    "origin": origin,
                },
            }
    except Exception:
        pass

    out = {"card": card, "meta": {}}
    out["meta"]["db_attached"] = db is not None
    out["meta"]["db_source"] = db_source
    out["meta"]["db_target"] = db_target
    if db is None and db_err:
        out["meta"]["db_error"] = db_err

    return JSONResponse(out)
