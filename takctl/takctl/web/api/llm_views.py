from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from takctl.services.llm import llm_status
from takctl.services.llm_views.tactical_operations import TacticalInputsSnapshot

router = APIRouter(prefix="/api/llm", tags=["llm"])


@router.get("/status")
def api_llm_status() -> dict[str, Any]:
    class _Ctx: ...
    return llm_status(_Ctx())  # type: ignore


@router.post("/views/tactical")
def api_llm_view_tactical() -> dict[str, Any]:
    class _Ctx: ...
    s = llm_status(_Ctx())  # type: ignore
    inputs = TacticalInputsSnapshot().collect()

    return {
        "view": "tactical-operations",
        "engine": "local",  # selection logic later
        "reachable": bool((s.get("health") or {}).get("ok", False)),
        "summary": "not implemented",
        "inputs": inputs,
        "llm": s,
    }
