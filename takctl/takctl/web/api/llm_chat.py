from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body

from takctl.services.llm import llm_status
from takctl.services.llm_http import http_post_json

router = APIRouter(prefix="/api/llm", tags=["llm"])


@router.get("/status")
def api_llm_status() -> dict[str, Any]:
    # Single source of truth (same status logic as CLI)
    return llm_status(None)


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
