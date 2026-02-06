from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Tuple

from fastapi import APIRouter, Body


from takctl.services.llm_extract import (
    extract_json_from_text as _extract_json_from_text,
    strip_code_fences as _strip_code_fences,
)

router = APIRouter(prefix="/api/llm", tags=["llm"])


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def _env(name: str, default: str) -> str:
    v = (os.environ.get(name) or "").strip()
    return v or default


def _read_prompt_pack(view: str) -> dict[str, str]:
    """
    Read prompt pack from deployed runtime path (installer-owned output).
    Required files:
      - system.txt
      - user.txt
    """
    root = Path("/opt/tak/tools/takctl/llm/prompt-packs") / view
    system_txt = (root / "system.txt").read_text(encoding="utf-8")
    user_txt = (root / "user.txt").read_text(encoding="utf-8")
    return {
        "system": system_txt.strip(),
        "user": user_txt.strip(),
        "path": str(root),
    }


def _http_json(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    timeout_sec: float = 12.0,
) -> tuple[int, Any, str | None]:
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
            pass
        return int(e.code), {"error": str(e), "body": body}, "http_error"
    except Exception as e:
        return 0, {"error": repr(e)}, "exception"



def _placeholder_plan(view: str, llm_url: str, reason: str, raw_text: str | None = None) -> dict[str, Any]:
    blocks = [
        {
            "type": "markdown",
            "title": "LLM Plan",
            "body": "LLM unavailable or returned invalid JSON. This is a placeholder plan.",
        }
    ]
    if raw_text:
        blocks.append(
            {
                "type": "markdown",
                "title": "LLM Raw Output",
                "body": raw_text,
            }
        )

    return {
        "blocks": blocks,
        "datasets": {},
        "meta": {
            "mode": "heuristic",
            "view": view,
            "llm_url": llm_url,
            "fallback_reason": reason,
        },
    }


# -----------------------------------------------------------------------------
# Status
# -----------------------------------------------------------------------------

def llm_status() -> dict[str, Any]:
    llm_url = _env("TAKS_LLM_URL", "http://127.0.0.1:8090")
    unit = "llm-local.service"

    code, data, err = _http_json("GET", f"{llm_url}/health", None, timeout_sec=2.0)
    if code == 200:
        return {
            "health": {"ok": True},
            "url": llm_url,
            "systemd_unit": unit,
        }

    return {
        "health": {"ok": False, "error": "unreachable", "detail": str(data or err)},
        "url": llm_url,
        "systemd_unit": unit,
    }


@router.get("/status")
def api_llm_status() -> dict[str, Any]:
    return llm_status()


# -----------------------------------------------------------------------------
# Plan generation
# -----------------------------------------------------------------------------

@router.post("/plan")
def api_llm_plan(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    """
    Generate a plan using llama.cpp via /v1/completions.
    """
    view = (payload.get("view") or "tactical-operations").strip()
    model = (payload.get("model") or "local-small").strip()
    max_tokens = int(payload.get("max_tokens") or 256)

    status = llm_status()
    llm_url = status.get("url")

    if not bool((status.get("health") or {}).get("ok")):
        return _placeholder_plan(view, llm_url, f"llm_unreachable {status.get('health')}")

    pack = _read_prompt_pack(view)

    prompt = (
        pack["system"]
        + "\n\n"
        + pack["user"]
        + "\n\nReturn ONLY valid JSON."
    )

    req = {
        "model": model,
        "prompt": prompt,
        "max_tokens": max_tokens,
        "stream": False,
    }

    code, data, err = _http_json(
        "POST",
        f"{llm_url}/v1/completions",
        req,
        timeout_sec=20.0,
    )

    raw_text = None
    if code == 200 and isinstance(data, dict):
        try:
            raw_text = ((data.get("choices") or [{}])[0] or {}).get("text")
        except Exception:
            raw_text = None

    extracted, extract_err, candidate = _extract_json_from_text(raw_text or "")
    if extracted is not None:
        return {
            "blocks": [
                {"type": "markdown", "title": "LLM Plan", "body": "Parsed JSON from LLM output."},
                {"type": "json", "title": "LLM JSON", "body": extracted},
            ],
            "datasets": {},
            "meta": {
                "mode": "llm",
                "view": view,
                "llm_url": llm_url,
            },
        }

    return _placeholder_plan(
        view,
        llm_url,
        f"llm_output_not_json err={extract_err}",
        raw_text=candidate,
    )


# -----------------------------------------------------------------------------
# Tactical view (stub)
# -----------------------------------------------------------------------------

@router.post("/views/tactical")
def api_llm_view_tactical() -> dict[str, Any]:
    s = llm_status()
    return {
        "view": "tactical-operations",
        "engine": "local",
        "reachable": bool((s.get("health") or {}).get("ok")),
        "summary": "not implemented",
        "inputs": {"ok": True, "note": "snapshot not wired yet"},
        "llm": s,
    }

