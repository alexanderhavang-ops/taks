from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Tuple

from takctl.config import load_config
from takctl.services.llm_http import http_post_json


def _http_timeout_sec() -> float:
    """
    Default LLM HTTP timeout from runtime conf.d.
    Generation on CPU can exceed 90s easily.
    """
    cfg = load_config()
    try:
        return float(cfg.llm_timeout_s)
    except Exception:
        return 600.0


@dataclass
class LLMClient:
    llm_url: str
    model: str = "local-small"

    def completions_debug(
        self,
        prompt: str,
        *,
        max_tokens: int = 800,
        temperature: float = 0.0,
        timeout_sec: float | None = None,
    ) -> Tuple[str, int, Any, Optional[str]]:
        """
        Calls llama.cpp OpenAI-compatible completions endpoint:
          POST {llm_url}/v1/completions

        Returns: (text, http_code, body(parsed_json_or_text), err)
        IMPORTANT: 'text' is the raw choices[0].text (no stripping/sanitization).
        """
        base = (self.llm_url or "").rstrip("/")
        if not base:
            raise RuntimeError("llm_url is empty")

        req: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "max_tokens": int(max_tokens),
            "temperature": float(temperature),
            "stream": False,
        }

        code, body, err = http_post_json(
            f"{base}/v1/completions",
            payload=req,
            timeout_sec=float(timeout_sec if timeout_sec is not None else _http_timeout_sec()),
        )

        if code != 200 or not isinstance(body, dict):
            raise RuntimeError(f"LLM HTTP error: code={code} err={err} body_type={type(body).__name__}")

        try:
            txt = ((body.get("choices") or [{}])[0] or {}).get("text") or ""
        except Exception:
            txt = ""

        return str(txt), int(code), body, err

    def completions_text(
        self,
        prompt: str,
        *,
        max_tokens: int = 800,
        temperature: float = 0.0,
        timeout_sec: float | None = None,
    ) -> str:
        """
        Backwards-compatible: return ONLY raw text.
        """
        txt, _code, _body, _err = self.completions_debug(
            prompt, max_tokens=max_tokens, temperature=temperature, timeout_sec=timeout_sec
        )
        return txt


def build_llm_client_from_env() -> LLMClient:
    """
    Backwards-compatible helper name.
    Actual source of truth is runtime conf.d.
    """
    cfg = load_config()
    llm_url = (cfg.llm_url or "http://127.0.0.1:8090").strip()
    model = (cfg.llm_model or "local-small").strip()
    return LLMClient(llm_url=llm_url, model=model)
