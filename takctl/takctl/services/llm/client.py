from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import requests


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


def _http_timeout_sec() -> float:
    """
    Default LLM HTTP timeout.
    CPU generation can be slow. Override with TAKS_LLM_HTTP_TIMEOUT_SEC.
    """
    return _env_float("TAKS_LLM_HTTP_TIMEOUT_SEC", 600.0)


@dataclass
class LLMClient:
    """
    Minimal OpenAI-compatible /v1/completions client.

    IMPORTANT:
      - Phase2 expects completions_debug() for tracing.
      - Phase3 (and others) use completions_text().

    This keeps deterministic knobs (seed/stop/timeout) and restores the debug-return
    signature used by the LLM runs pipeline.
    """
    llm_url: str
    model: str = "local-small"

    def __post_init__(self) -> None:
        self.llm_url = (self.llm_url or "").strip().rstrip("/") or "http://127.0.0.1:8090"
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
    ) -> Tuple[str, int, Any, Optional[str]]:
        """
        POST {llm_url}/v1/completions

        Returns: (text, http_code, body(parsed_json_or_text), err)
        - Never raises for HTTP status; errors are returned in (code, body, err).
        - 'text' is raw choices[0].text if present; else "".
        """
        base = (self.llm_url or "").rstrip("/")
        if not base:
            return ("", 0, None, "llm_url is empty")

        # Defaults / determinism knobs
        if seed is None:
            seed = _env_int("LLM_SEED", 0)
        if stop is None:
            stop = _parse_stop_env()
        if timeout_sec is None:
            timeout_sec = _http_timeout_sec()

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

        url = f"{base}/v1/completions"
        t0 = time.time()

        try:
            r = requests.post(
                url,
                headers={"content-type": "application/json"},
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                timeout=float(timeout_sec),
            )
            code = int(r.status_code)

            # Parse body (json if possible, else text)
            body: Any
            try:
                body = r.json()
            except Exception:
                body = r.text

            err: Optional[str] = None
            if code != 200:
                err = f"http_{code}"

            # Optional tiny debug line (no prompt dump)
            if _env_str("LLM_DEBUG", "").lower() in ("1", "true", "yes", "on"):
                dt_ms = int((time.time() - t0) * 1000)
                print(
                    "[llm_client] "
                    + json.dumps(
                        {
                            "url": url,
                            "status": code,
                            "dt_ms": dt_ms,
                            "max_tokens": payload.get("max_tokens"),
                            "temperature": payload.get("temperature"),
                            "seed": payload.get("seed"),
                            "stop": payload.get("stop", None),
                            "model": payload.get("model", None),
                        },
                        ensure_ascii=False,
                    )
                )

            txt = ""
            if isinstance(body, dict):
                try:
                    txt = ((body.get("choices") or [{}])[0] or {}).get("text") or ""
                except Exception:
                    txt = ""

            return (str(txt), code, body, err)

        except Exception as e:
            return ("", 0, None, f"{type(e).__name__}: {e}")

    def completions(
        self,
        prompt: str,
        *,
        max_tokens: int = 512,
        temperature: float = 0.0,
        timeout_sec: int = 120,
        seed: Optional[int] = None,
        stop: Optional[list[str]] = None,
    ) -> Dict[str, Any]:
        """
        Backwards-compatible: return parsed JSON dict (or an error dict).
        Some codepaths use this "dict-only" API.
        """
        txt, code, body, err = self.completions_debug(
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout_sec=float(timeout_sec),
            seed=seed,
            stop=stop,
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
        timeout_sec: int = 120,
        seed: Optional[int] = None,
        stop: Optional[list[str]] = None,
    ) -> str:
        """
        Convenience: returns the first choice text (or empty string).
        """
        obj = self.completions(
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout_sec=timeout_sec,
            seed=seed,
            stop=stop,
        )
        if not isinstance(obj, dict):
            return ""
        try:
            return str(((obj.get("choices") or [{}])[0] or {}).get("text") or "")
        except Exception:
            return ""


def build_llm_client_from_env() -> LLMClient:
    """
    Small helper used by LLM plumbing.
    """
    llm_url = (_env_str("TAKS_LLM_URL", "http://127.0.0.1:8090") or "http://127.0.0.1:8090").strip()
    model = (_env_str("TAKS_LLM_MODEL", "local-small") or "local-small").strip()
    return LLMClient(llm_url=llm_url, model=model)
