from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body

from takctl.services.llm import llm_status
from takctl.services.llm_http import http_post_json
from takctl.services.llm_planner import plan_with_tools
from takctl.services.snapshots.tactical import build_tactical_snapshot

router = APIRouter(prefix="/api/llm", tags=["llm"])


# -----------------------------------------------------------------------------
# Status
# -----------------------------------------------------------------------------

@router.get("/status")
def api_llm_status() -> dict[str, Any]:
    # single source of truth (same as CLI uses)
    return llm_status(None)


# -----------------------------------------------------------------------------
# Fast dev loop: "any prompt" chat (no tools, no schema, just raw model behavior)
# -----------------------------------------------------------------------------

@router.post("/chat")
def api_llm_chat(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    """
    Development-speed endpoint.

    Sends a raw prompt to llama.cpp /v1/completions and returns raw text.
    This is intentionally NOT a planner and NOT a renderplan.
    """
    status = llm_status(None)
    llm_url = (status.get("url") or "http://127.0.0.1:8090").rstrip("/")

    if not bool((status.get("health") or {}).get("ok")):
        return {
            "ok": False,
            "error": "llm_unreachable",
            "detail": status.get("health"),
            "llm_url": llm_url,
        }

    prompt = str(payload.get("prompt") or "").strip()
    if not prompt:
        return {"ok": False, "error": "missing_prompt"}

    model = str(payload.get("model") or "local-small").strip()
    max_tokens = int(payload.get("max_tokens") or 256)
    temperature = float(payload.get("temperature") or 0.0)

    req = {
        "model": model,
        "prompt": prompt,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
    }

    code, body, err = http_post_json(f"{llm_url}/v1/completions", req, timeout_sec=60.0)

    raw_text = ""
    if code == 200 and isinstance(body, dict):
        try:
            raw_text = str(((body.get("choices") or [{}])[0] or {}).get("text") or "")
        except Exception:
            raw_text = ""

    return {
        "ok": bool(code == 200),
        "http": code,
        "error": err,
        "llm_url": llm_url,
        "model": model,
        "text": raw_text,
        "raw": body if isinstance(body, dict) else {"body": body},
    }


# -----------------------------------------------------------------------------
# Planner: tool-iterative planning (db.query) -> final RenderPlan
# -----------------------------------------------------------------------------

@router.post("/plan")
def api_llm_plan(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    """
    Generate a RenderPlan using the tool-iterative planner.

    Input is a snapshot bundle (deterministic input).
    Output is a RenderPlan (stable output contract).
    """
    view = str(payload.get("view") or "tactical-operations").strip()

    # Snapshot can be provided by caller (tests) or built here in view endpoints.
    snapshot = payload.get("snapshot")
    if not isinstance(snapshot, dict):
        snapshot = {"ts_utc": None, "notes": ["missing snapshot"], "postgres": {}}

    model = str(payload.get("model") or "local-small").strip()
    max_iters = int(payload.get("max_iters") or 6)
    max_tokens = int(payload.get("max_tokens") or 450)

    return plan_with_tools(
        view=view,
        snapshot=snapshot,
        model=model,
        max_iters=max_iters,
        max_tokens=max_tokens,
    )


# -----------------------------------------------------------------------------
# Tactical view: snapshot + planner -> final RenderPlan (UI renders blocks)
# -----------------------------------------------------------------------------

@router.post("/views/tactical")
def api_llm_view_tactical() -> dict[str, Any]:
    """
    End-to-end tactical view:
      - Build snapshot (bounded, deterministic)
      - Run tool-iterative planner against DB
      - Return final RenderPlan (what CLI + Web both render)
    """
    snapshot = build_tactical_snapshot()

    plan = plan_with_tools(
        view="tactical-operations",
        snapshot=snapshot,
        model="local-small",
        max_iters=6,
        max_tokens=450,
    )

    return plan

