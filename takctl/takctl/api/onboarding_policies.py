from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from takctl.onboarding.policy_registry import default_policy_id, get_doc_path, get_policy, list_policies

router = APIRouter(tags=["onboarding"])


@router.get("/onboarding/policies")
def policies_list():
    ps = list_policies()
    return JSONResponse(
        {
            "default_policy_id": default_policy_id(),
            "policies": [
                {
                    "id": p.policy_id,
                    "name": p.name,
                    "version": p.version,
                    "source": p.source,
                    "has_doc": bool(p.has_doc),
                    "doc_url": (f"/api/onboarding/policies/{p.policy_id}/doc" if p.has_doc else None),
                }
                for p in ps
            ],
        },
        headers={"cache-control": "no-store, max-age=0", "pragma": "no-cache"},
    )


@router.get("/onboarding/policies/{policy_id}")
def policy_get(policy_id: str):
    try:
        j = get_policy(policy_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Unknown policy")
    return JSONResponse(j, headers={"cache-control": "no-store, max-age=0", "pragma": "no-cache"})


@router.get("/onboarding/policies/{policy_id}/doc", include_in_schema=False)
def policy_doc(policy_id: str):
    p = get_doc_path(policy_id)
    if not p:
        raise HTTPException(status_code=404, detail="No doc for policy")
    return FileResponse(path=str(p), media_type="application/pdf")
