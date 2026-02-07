from __future__ import annotations

from typing import Any, Optional

from takctl.services.llm_http import http_get_json, http_post_json


def llm_health(llm_url: str) -> dict[str, Any]:
    base = (llm_url or "").rstrip("/")
    code, body, err = http_get_json(f"{base}/health", timeout_sec=2.0)
    ok = bool(code == 200 and isinstance(body, dict) and body.get("status") == "ok")
    return {
        "ok": ok,
        "status_code": code or None,
        "body": body,
        "error": err,
    }


def llm_completion(
    *,
    llm_url: str,
    prompt: str,
    model: str = "local-small",
    max_tokens: int = 256,
    temperature: float = 0.2,
    timeout_sec: float = 60.0,
) -> dict[str, Any]:
    """
    Thin wrapper around llama.cpp OpenAI-compatible:
      POST {llm_url}/v1/completions

    Returns:
      {
        "ok": bool,
        "text": str,
        "status_code": int|None,
        "error": str|None,
        "raw": dict|None
      }
    """
    base = (llm_url or "").rstrip("/")
    req: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "max_tokens": int(max_tokens),
        "temperature": float(temperature),
        "stream": False,
    }

    code, body, err = http_post_json(
        f"{base}/v1/completions",
        payload=req,
        timeout_sec=float(timeout_sec),
    )

    text: str = ""
    if code == 200 and isinstance(body, dict):
        try:
            text = str((((body.get("choices") or [{}])[0]) or {}).get("text") or "")
        except Exception:
            text = ""

    ok = bool(code == 200 and isinstance(body, dict) and text != "")
    return {
        "ok": ok,
        "text": text,
        "status_code": (code or None),
        "error": err,
        "raw": body,
    }

