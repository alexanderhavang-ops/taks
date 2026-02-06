from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from fastapi import Body

router = APIRouter(prefix="/api/llm", tags=["llm"])


def _env(name: str, default: str) -> str:
    v = (os.environ.get(name) or "").strip()
    return v or default


def _read_prompt_pack(view: str) -> dict[str, str]:
    """
    Read prompt pack from deployed runtime path (installer-owned output).
    Required: system.txt + user.txt
    """
    root = Path("/opt/tak/tools/takctl/llm/prompt-packs") / view
    system_txt = (root / "system.txt").read_text(encoding="utf-8")
    user_txt = (root / "user.txt").read_text(encoding="utf-8")
    return {"system": system_txt.strip(), "user": user_txt.strip(), "path": str(root)}


def _http_json(method: str, url: str, payload: dict[str, Any] | None = None, timeout_sec: float = 12.0) -> tuple[int, Any, str | None]:
    import urllib.request
    import urllib.error

    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as r:
            code = int(getattr(r, "status", 200))
            raw = r.read().decode("utf-8", "replace").strip()
            if not raw:
                return code, None, None
            try:
                return code, json.loads(raw), None
            except Exception:
                return code, raw, "non_json_response"
    except urllib.error.HTTPError as e:
        body = None
        try:
            body = e.read().decode("utf-8", "replace").strip()
        except Exception:
            body = None
        return int(getattr(e, "code", 0) or 0), {"error": str(e), "body": body}, "http_error"
    except Exception as e:
        return 0, {"error": repr(e)}, "exception"


def llm_status() -> dict[str, Any]:
    llm_url = _env("TAKS_LLM_URL", "http://127.0.0.1:8091")
    unit = _env("TAKS_LLM_SYSTEMD_UNIT", "llm-local.service")

    code, data, err = _http_json("GET", f"{llm_url}/health", None, timeout_sec=2.0)
    if code == 200 and isinstance(data, dict) and data.get("status") == "ok":
        return {"health": {"ok": True}, "url": llm_url, "systemd_unit": unit}

    return {"health": {"ok": False, "error": "unreachable", "detail": f"code={code} err={err} data={data}"}, "url": llm_url, "systemd_unit": unit}


def _strip_code_fences(s: str) -> str:
    t = s.strip()
    if t.startswith("```"):
        # remove first fence line
        t = t.split("\n", 1)[1] if "\n" in t else ""
        # remove trailing fence
        if "```" in t:
            t = t.rsplit("```", 1)[0]
    return t.strip()


def _placeholder_plan(view: str, llm_url: str, reason: str, raw_text: str | None = None) -> dict[str, Any]:
    blocks = [{
        "type": "markdown",
        "title": "LLM Plan",
        "body": "LLM unavailable or returned invalid JSON. This is a placeholder plan.",
    }]
    if raw_text:
        blocks.append({
            "type": "markdown",
            "title": "LLM Raw Output",
            "body": raw_text.strip()[:8000],
        })
    return {
        "blocks": blocks,
        "datasets": {},
        "meta": {"mode": "heuristic", "view": view, "llm_url": llm_url, "fallback_reason": reason},
    }


@router.get("/status")
def api_llm_status() -> dict[str, Any]:
    return llm_status()


@router.post("/views/tactical")
def api_llm_view_tactical() -> dict[str, Any]:
    s = llm_status()
    return {
        "view": "tactical-operations",
        "engine": "local",
        "reachable": bool((s.get("health") or {}).get("ok", False)),
        "summary": "not implemented",
        "inputs": {"ok": True, "note": "snapshot not wired yet"},
        "llm": s,
    }


@router.post("/plan")
def api_llm_plan(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    """
    Generate a plan JSON document.
    For now we call llama.cpp OpenAI-compatible *text* completions endpoint:
      POST {llm_url}/v1/completions
    and expect the model to return JSON in choices[0].text.
    """
    view = (payload.get("view") or "tactical-operations").strip()
    model = (payload.get("model") or "local-small").strip()
    max_tokens = int(payload.get("max_tokens") or 256)

    s = llm_status()
    llm_url = str(s.get("url") or _env("TAKS_LLM_URL", "http://127.0.0.1:8091"))
    if not bool((s.get("health") or {}).get("ok", False)):
        return _placeholder_plan(view, llm_url, f"llm_unreachable {s.get('health')}")

    pack = _read_prompt_pack(view)

    # Keep it dead simple: concatenate the prompt-pack.
    prompt = (
        pack["system"].strip()
        + "\n\n"
        + pack["user"].strip()
        + "\n\n"
        + "Return ONLY valid JSON."
    )

    req = {
        "model": model,
        "prompt": prompt,
        "max_tokens": max_tokens,
        "stream": False,
    }

    code, data, err = _http_json("POST", f"{llm_url}/v1/completions", req, timeout_sec=20.0)

    # Expected OpenAI-ish response:
    # { choices: [ { text: "..." } ], ... }
    raw_text = None
    if code == 200 and isinstance(data, dict):
        try:
            raw_text = ((data.get("choices") or [{}])[0] or {}).get("text")
        except Exception:
            raw_text = None

    if not raw_text or not isinstance(raw_text, str):
        return _placeholder_plan(view, llm_url, f"llm_bad_response code={code} err={err} data_type={type(data).__name__}", raw_text=None)

    candidate = _strip_code_fences(raw_text)
    try:
        obj = json.loads(candidate)
        if isinstance(obj, dict) and "blocks" in obj and "datasets" in obj:
            # Add a tiny meta breadcrumb if missing
            meta = obj.get("meta") if isinstance(obj.get("meta"), dict) else {}
            meta.setdefault("mode", "llm")
            meta.setdefault("view", view)
            meta.setdefault("llm_url", llm_url)
            obj["meta"] = meta
            return obj
        # If valid JSON but not our schema, still show it.
        return _placeholder_plan(view, llm_url, "llm_json_not_plan_schema", raw_text=candidate)
    except Exception as e:
        return _placeholder_plan(view, llm_url, f"llm_output_not_json err={repr(e)}", raw_text=candidate)
