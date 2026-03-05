from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from takctl.services.llm_http import http_post_json


def _env_str(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def _env_int(name: str, default: int) -> int:
    v = (os.environ.get(name) or "").strip()
    if not v:
        return default
    try:
        return int(v)
    except Exception:
        return default


def _env_float(name: str, default: float) -> float:
    v = (os.environ.get(name) or "").strip()
    if not v:
        return default
    try:
        return float(v)
    except Exception:
        return default


def _parse_stop_env() -> Optional[list[str]]:
    """
    LLM_STOP="END,---" -> ["END","---"]
    Empty -> None
    """
    raw = _env_str("LLM_STOP", "")
    if not raw:
        return None
    parts = [p.strip() for p in raw.split(",")]
    out = [p for p in parts if p]
    return out or None


@dataclass
class LLMClient:
    """
    Minimal OpenAI-compatible /v1/completions client.

    Contract:
      - Phase2 expects completions_debug() returning (text, http_code, body, err)
      - Other codepaths may call completions() (dict) or completions_text() (str)

    Implementation:
      - Uses takctl.services.llm_http.http_post_json (no external deps).
      - Determinism knobs via env:
          LLM_SEED (int), LLM_STOP (comma list), LLM_DEBUG (bool-ish),
          TAKS_LLM_HTTP_TIMEOUT_SEC (float)
    """
    llm_url: str
    model: str = "local-small"

    def __post_init__(self) -> None:
        base = (self.llm_url or "").strip().rstrip("/")
        self.llm_url = base or "http://127.0.0.1:8090"
        self.model = (self.model or "").strip() or "local-small"

    def completions_debug(
        self,
        prompt: str,
        *,
        max_tokens: int = 512,
        temperature: float = 0.0,
        timeout_sec: float | None = None,
        seed: Optional[int] = None,
        stop: Optional[list[str]] = None,
        json_schema: Any | None = None,
        grammar: str | None = None,
    ) -> Tuple[str, int, Any, Optional[str]]:
        base = (self.llm_url or "").rstrip("/")
        if not base:
            return ("", 0, None, "llm_url is empty")

        if seed is None:
            seed = _env_int("LLM_SEED", 0)
        if stop is None:
            stop = _parse_stop_env()
        if timeout_sec is None:
            timeout_sec = _env_float("TAKS_LLM_HTTP_TIMEOUT_SEC", 600.0)

        payload: Dict[str, Any] = {
            "model": self.model,
            "prompt": str(prompt or ""),
            "max_tokens": int(max_tokens),
            "temperature": float(temperature),
            "seed": int(seed) if seed is not None else 0,
            "stream": False,
        }
        if stop:
            payload["stop"] = stop

        # llama.cpp server extensions (best-effort; ignored if unsupported)
        if json_schema is not None:
            payload["json_schema"] = json_schema
        if grammar:
            payload["grammar"] = grammar

        url = f"{base}/v1/completions"
        t0 = time.time()

        code, body, err = http_post_json(url, payload=payload, timeout_sec=float(timeout_sec))

        if _env_str("LLM_DEBUG", "").lower() in ("1", "true", "yes", "on"):
            dt_ms = int((time.time() - t0) * 1000)
            print(
                "[llm_client] "
                + str(
                    {
                        "url": url,
                        "status": code,
                        "dt_ms": dt_ms,
                        "max_tokens": payload.get("max_tokens"),
                        "temperature": payload.get("temperature"),
                        "seed": payload.get("seed"),
                        "stop": payload.get("stop", None),
                        "has_json_schema": "json_schema" in payload,
                        "has_grammar": "grammar" in payload,
                        "err": err,
                    }
                )
            )

        txt = ""
        if isinstance(body, dict):
            try:
                txt = ((body.get("choices") or [{}])[0] or {}).get("text") or ""
            except Exception:
                txt = ""

        if code != 200 and not err:
            err = f"http_{code}"

        return (str(txt), int(code or 0), body, err)

    def completions(
        self,
        prompt: str,
        *,
        max_tokens: int = 512,
        temperature: float = 0.0,
        timeout_sec: float | None = None,
        seed: Optional[int] = None,
        stop: Optional[list[str]] = None,
        json_schema: Any | None = None,
        grammar: str | None = None,
    ) -> Dict[str, Any]:
        txt, code, body, err = self.completions_debug(
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout_sec=timeout_sec,
            seed=seed,
            stop=stop,
            json_schema=json_schema,
            grammar=grammar,
        )
        if code != 200 or not isinstance(body, dict):
            return {"ok": False, "error": err or f"http_{code}", "code": code, "raw": body, "text": txt}
        return body

    def completions_text(
        self,
        prompt: str,
        *,
        max_tokens: int = 512,
        temperature: float = 0.0,
        timeout_sec: float | None = None,
        seed: Optional[int] = None,
        stop: Optional[list[str]] = None,
        json_schema: Any | None = None,
        grammar: str | None = None,
    ) -> str:
        obj = self.completions(
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout_sec=timeout_sec,
            seed=seed,
            stop=stop,
            json_schema=json_schema,
            grammar=grammar,
        )
        if isinstance(obj, dict):
            try:
                return str(((obj.get("choices") or [{}])[0] or {}).get("text") or "")
            except Exception:
                return ""
        return ""


def build_llm_client_from_env() -> LLMClient:
    llm_url = _env_str("TAKS_LLM_URL", "http://127.0.0.1:8090")
    model = _env_str("TAKS_LLM_MODEL", "local-small")
    return LLMClient(llm_url=llm_url, model=model)
