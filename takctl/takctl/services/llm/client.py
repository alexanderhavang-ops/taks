from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from takctl.services.llm_http import http_post_json


@dataclass
class LLMClient:
    llm_url: str
    model: str = "local-small"

    def completions_text(
        self,
        prompt: str,
        *,
        max_tokens: int = 800,
        temperature: float = 0.0,
        timeout_sec: float = 90.0,
    ) -> str:
        """
        Calls llama.cpp OpenAI-compatible completions endpoint:
          POST {llm_url}/v1/completions

        Returns raw text (best-effort).
        Raises RuntimeError on HTTP/parse failures.
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
            timeout_sec=float(timeout_sec),
        )
        if code != 200 or not isinstance(body, dict):
            raise RuntimeError(
                f"LLM HTTP error: code={code} err={err} body_type={type(body).__name__}"
            )

        try:
            txt = ((body.get("choices") or [{}])[0] or {}).get("text") or ""
        except Exception:
            txt = ""
        return str(txt)


def build_llm_client_from_env() -> LLMClient:
    """
    Backwards-compatible helper used by takctl.services.llmchat.
    Keep it tiny and deterministic.
    """
    llm_url = (os.environ.get("TAKS_LLM_URL") or "http://127.0.0.1:8090").strip()
    model = (os.environ.get("TAKS_LLM_MODEL") or "local-small").strip()
    return LLMClient(llm_url=llm_url, model=model)
