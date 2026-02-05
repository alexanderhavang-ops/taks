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


import json
import os
from pathlib import Path as _Path

from fastapi import Body
# NOTE: Optional import. Web must load even if heuristic renderer moved/changed.
try:
    from takctl.render.tactical_json import build_tactical_plan  # type: ignore
except Exception:
    build_tactical_plan = None  # type: ignore

def _env(name: str, default: str) -> str:
    v = (os.environ.get(name) or "").strip()
    return v or default


def _read_prompt_pack(view: str) -> dict[str, str]:
    """
    Read prompt pack from deployed runtime path (installer-owned output).
    Required: system.txt + user.txt
    """
    root = _Path("/opt/tak/tools/takctl/llm/prompt-packs") / view
    system_txt = (root / "system.txt").read_text(encoding="utf-8")
    user_txt = (root / "user.txt").read_text(encoding="utf-8")
    return {"system": system_txt.strip(), "user": user_txt.strip(), "path": str(root)}


def _http_post_json(url: str, payload: dict[str, Any], timeout_sec: float = 12.0) -> tuple[int, Any, str | None]:
    # Local tiny helper to avoid importing the CLI service layer here.
    import urllib.request

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


@router.post("/plan")
def api_llm_plan(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """
    Produce a RenderPlan for a view by calling the local llama.cpp server using the
    OpenAI-compatible endpoint (/v1/chat/completions).

    Input payload (suggested):
      {
        "view": "tactical-operations",
        "title": "Tactical Operations",
        "data": {...}   # snapshot/inputs for the view
      }

    Output:
      RenderPlan dict: { "blocks": [...], "datasets": {...}, "meta": {...} }
    """
    view = str(payload.get("view") or "tactical-operations")
    title = str(payload.get("title") or "LLM Plan")
    data = payload.get("data") or {}

    # Load prompt pack (runtime deployed)
    pack = _read_prompt_pack(view)

    # LLM endpoint
    base = _env("TAKS_LLM_URL", "http://127.0.0.1:8090").rstrip("/")
    url = f"{base}/v1/chat/completions"

    # Enforce: “Return RenderPlan JSON ONLY”
    schema_hint = (
        "You MUST respond with valid JSON only (no markdown, no prose). "
        "The JSON MUST be a RenderPlan object with keys: blocks (list), datasets (object), meta (object).\n"
        "Do not include any additional top-level keys.\n"
        "Keep datasets small; summarize, aggregate, and sample where needed.\n"
    )

    messages = [
        {"role": "system", "content": pack["system"]},
        {"role": "system", "content": schema_hint},
        {"role": "user", "content": pack["user"]},
        {"role": "user", "content": f"TITLE: {title}\n\nINPUT_DATA_JSON:\n{json.dumps(data)[:200000]}"},
    ]

    # llama.cpp OpenAI-compatible request
    req = {
        "model": "local-small",   # matches --alias local-small
        "messages": messages,
        "temperature": 0.2,
    }

    code, body, err = _http_post_json(url, req, timeout_sec=18.0)

    # Extract assistant content
    content = None
    if code == 200 and isinstance(body, dict):
        try:
            content = body["choices"][0]["message"]["content"]
        except Exception:
            content = None

    # Try parse RenderPlan JSON
    if isinstance(content, str):
        try:
            plan = json.loads(content)
            if isinstance(plan, dict) and "blocks" in plan and "datasets" in plan:
                meta = dict(plan.get("meta") or {})
                meta.update(
                    {
                        "mode": "llm",
                        "view": view,
                        "llm_url": base,
                        "prompt_pack_path": pack["path"],
                    }
                )
                plan["meta"] = meta
                return plan
        except Exception:
            pass

    # Fallback: heuristic plan
    rp = build_tactical_plan(data, title=title)
    out = rp.to_dict()
    out["meta"] = dict(out.get("meta") or {})
    out["meta"].update(
        {
            "mode": "heuristic",
            "view": view,
            "fallback_reason": f"llm_invalid_or_unreachable http={code or 'n/a'} err={err or 'n/a'}",
            "llm_url": base,
            "prompt_pack_path": pack.get("path"),
        }
    )
    # Include minimal debug (bounded)
    out["meta"]["llm_debug"] = {
        "http": code,
        "error": err,
        "raw_type": type(body).__name__ if body is not None else None,
    }
    return out
