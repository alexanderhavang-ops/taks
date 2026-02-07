from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from takctl.services.llm import llm_status
from takctl.services.snapshots.tactical import build_tactical_snapshot

router = APIRouter(prefix="/api/llm", tags=["llm"])


@router.post("/views/tactical")
def api_llm_view_tactical() -> dict[str, Any]:
    """
    Tactical operations view.

    Responsibilities:
      - Collect a deterministic snapshot
      - Report LLM reachability
      - Return a stable, UI-agnostic structure

    This endpoint:
      - Does NOT talk to the database directly
      - Does NOT know SQL or schema details
      - Does NOT invoke the LLM
    """
    snapshot = build_tactical_snapshot()
    s = llm_status(None)

    return {
        "view": "tactical-operations",
        "engine": "local",
        "reachable": bool((s.get("health") or {}).get("ok")),
        "inputs": {
            "ok": True,
            "snapshot": snapshot,
        },
        "llm": s,
    }

