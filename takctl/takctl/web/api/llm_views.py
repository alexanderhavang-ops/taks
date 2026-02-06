from __future__ import annotations

import json
import os
import urllib.request
from typing import Any

from fastapi import APIRouter
from fastapi import Body
, Body

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
def api_llm_plan(body: dict = Body(default={})):
    """
    Minimal LLM plan endpoint:
    - loads prompt pack (system.txt + user.txt) by view
    - calls llama.cpp /v1/chat/completions
    - returns raw JSON response (no rendering)
    """
    view = (body.get("view") or "tactical-operations").strip()
    model = (body.get("model") or "local-small").strip()
    temperature = float(body.get("temperature", 0.2))
    max_tokens = int(body.get("max_tokens", 256))
    timeout = float(body.get("timeout_sec", 12.0))

    # Prefer inline prompt override, else prompt-pack on disk
    pack = None
    system = (body.get("system") or "").strip()
    user = (body.get("user") or "").strip()
    if not system or not user:
        try:
            pack = _read_prompt_pack(view)
            system = system or pack["system"]
            user = user or pack["user"]
        except Exception as e:
            # If caller provided inline prompts, we can still proceed.
            if not system or not user:
                return {
                    "ok": False,
                    "error": "prompt_pack_missing",
                    "detail": repr(e),
                    "view": view,
                }

    # LLM base URL (from env, consistent with /api/llm/status)
    base = _env("TAKS_LLM_URL", "http://127.0.0.1:8090").rstrip("/")
    endpoint = base + "/v1/chat/completions"

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }

    code, resp, err = _http_post_json(endpoint, payload, timeout_sec=timeout)
    ok = (code >= 200 and code < 300 and err is None)

    return {
        "ok": ok,
        "endpoint": endpoint,
        "http_code": code,
        "error": err,
        "view": view,
        "prompt_pack": pack,
        "request": {
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
        "response": resp,
    }
