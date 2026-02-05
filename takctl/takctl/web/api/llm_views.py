from __future__ import annotations

import json
import os
import urllib.request
from typing import Any

from fastapi import APIRouter, Body

router = APIRouter(prefix="/api/llm", tags=["llm"])


def _env(name: str, default: str) -> str:
    v = (os.environ.get(name) or "").strip()
    return v or default


def _http_post_json(url: str, payload: dict[str, Any], timeout_sec: float = 12.0) -> tuple[int, Any, str | None]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as r:
            code = int(getattr(r, "status", 200))
            raw = r.read().decode("utf-8", "replace").strip()
            if not raw:
                return code, None, None
            try:
                return code, json.loads(raw), None
            except Exception:
                return code, raw[:4000], "non-json-response"
    except Exception as e:
        return 0, None, str(e)


@router.get("/status")
def api_llm_status() -> dict[str, Any]:
    """
    Always safe. Does not import takctl.services.llm (which may be broken).
    Just reports configured LLM endpoint + a lightweight reachability probe.
    """
    base = _env("TAKS_LLM_URL", "http://127.0.0.1:8091").rstrip("/")
    unit = _env("TAKS_LLM_SYSTEMD_UNIT", "llm-local.service")

    # Cheap probe: call /v1/models (OpenAI-compat) if present, otherwise mark unknown
    url = f"{base}/v1/models"
    try:
        with urllib.request.urlopen(url, timeout=1.5) as r:
            ok = int(getattr(r, "status", 200)) == 200
    except Exception as e:
        ok = False
        return {
            "health": {"ok": False, "error": "unreachable", "detail": repr(e)},
            "url": base,
            "systemd_unit": unit,
        }

    return {
        "health": {"ok": bool(ok)},
        "url": base,
        "systemd_unit": unit,
    }


@router.post("/views/tactical")
def api_llm_view_tactical() -> dict[str, Any]:
    """
    Placeholder view endpoint: keeps UI plumbing working even before
    TacticalInputsSnapshot + render plan machinery is wired in.
    """
    s = api_llm_status()
    return {
        "view": "tactical-operations",
        "engine": "local",
        "reachable": bool((s.get("health") or {}).get("ok", False)),
        "summary": "not implemented",
        "inputs": {"ok": True, "note": "snapshot not wired yet"},
        "llm": s,
    }


@router.post("/plan")
def api_llm_plan(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """
    Minimal RenderPlan generator:
    - If llama.cpp is reachable: calls /v1/chat/completions and tries to parse JSON content.
    - Else: returns a trivial heuristic RenderPlan.
    No dependency on takctl.render.* or takctl.services.llm.
    """
    view = str(payload.get("view") or "tactical-operations")
    title = str(payload.get("title") or "LLM Plan")
    data = payload.get("data") or {}

    base = _env("TAKS_LLM_URL", "http://127.0.0.1:8091").rstrip("/")
    url = f"{base}/v1/chat/completions"

    schema_hint = (
        "You MUST respond with valid JSON only (no markdown, no prose). "
        "The JSON MUST be a RenderPlan object with keys: blocks (list), datasets (object), meta (object). "
        "Do not include any additional top-level keys."
    )

    messages = [
        {"role": "system", "content": schema_hint},
        {"role": "user", "content": f"TITLE: {title}\nVIEW: {view}\nINPUT_DATA_JSON:\n{json.dumps(data)[:200000]}"},
    ]

    req = {"model": "local-small", "messages": messages, "temperature": 0.2}
    code, body, err = _http_post_json(url, req, timeout_sec=12.0)

    content = None
    if code == 200 and isinstance(body, dict):
        try:
            content = body["choices"][0]["message"]["content"]
        except Exception:
            content = None

    if isinstance(content, str):
        try:
            plan = json.loads(content)
            if isinstance(plan, dict) and "blocks" in plan and "datasets" in plan and "meta" in plan:
                plan["meta"] = dict(plan.get("meta") or {})
                plan["meta"].update({"mode": "llm", "view": view, "llm_url": base})
                return plan
        except Exception:
            pass

    # Fallback (always-valid RenderPlan)
    return {
        "blocks": [
            {
                "type": "markdown",
                "title": title,
                "body": "LLM unavailable or returned invalid JSON. This is a placeholder plan.",
            }
        ],
        "datasets": {},
        "meta": {
            "mode": "heuristic",
            "view": view,
            "llm_url": base,
            "fallback_reason": f"llm_invalid_or_unreachable http={code or 'n/a'} err={err or 'n/a'}",
        },
    }
