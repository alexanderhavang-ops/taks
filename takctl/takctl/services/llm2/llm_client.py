from __future__ import annotations

import json
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from takctl.config import load_config, load_secrets


USAGE_LOG_PATH = Path("/opt/tak/tools/takctl/state/llm_usage.jsonl")


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _safe_int(v: Any, default: int) -> int:
    try:
        return int(v)
    except Exception:
        return default


def _s(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _safe_json_dumps(obj: Any) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False, sort_keys=True)
    except Exception:
        return "{}"


def _append_usage_log(rec: Dict[str, Any]) -> None:
    try:
        USAGE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with USAGE_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
    except Exception:
        pass


def _extract_usage_fields(provider: str, body_obj: Any) -> Dict[str, Any]:
    out = {
        "input_tokens": None,
        "output_tokens": None,
        "total_tokens": None,
    }

    try:
        if not isinstance(body_obj, dict):
            return out

        # Bedrock Converse commonly returns usage.{inputTokens,outputTokens,totalTokens}
        if provider == "bedrock":
            usage = body_obj.get("usage") or {}
            if isinstance(usage, dict):
                out["input_tokens"] = usage.get("inputTokens")
                out["output_tokens"] = usage.get("outputTokens")
                out["total_tokens"] = usage.get("totalTokens")
            return out

        # OpenAI-like completions may return usage.{prompt_tokens,completion_tokens,total_tokens}
        usage = body_obj.get("usage") or {}
        if isinstance(usage, dict):
            out["input_tokens"] = usage.get("prompt_tokens")
            out["output_tokens"] = usage.get("completion_tokens")
            out["total_tokens"] = usage.get("total_tokens")
    except Exception:
        pass

    return out


def _bedrock_geo_prefix(region: str) -> str:
    r = _s(region).lower()
    if r.startswith("us-"):
        return "us"
    if r.startswith("eu-"):
        return "eu"
    if r.startswith("ap-"):
        return "ap"
    if r.startswith("sa-"):
        return "sa"
    if r.startswith("ca-"):
        return "ca"
    return ""


def _normalize_bedrock_model_id(model_id: str, region: str) -> str:
    mid = _s(model_id)
    if not mid:
        return ""
    if len(mid) > 3 and mid[2] == ".":
        return mid
    pref = _bedrock_geo_prefix(region)
    if not pref:
        return mid
    return f"{pref}.{mid}"


def _http_post_json(
    url: str,
    payload: Dict[str, Any],
    *,
    timeout_s: int,
    headers: Optional[Dict[str, str]] = None,
) -> Tuple[int, bytes]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    hdrs = {"Content-Type": "application/json"}
    if headers:
        hdrs.update(headers)

    req = urllib.request.Request(url=url, method="POST", data=data, headers=hdrs)

    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            body = resp.read()
            return int(getattr(resp, "status", 0) or 0), body
    except urllib.error.HTTPError as e:
        try:
            body = e.read() or b""
        except Exception:
            body = b""
        return int(getattr(e, "code", 0) or 0), body


def _extract_openai_completions_text(body_obj: Any) -> str:
    try:
        if isinstance(body_obj, dict):
            choices = body_obj.get("choices") or []
            if choices and isinstance(choices[0], dict):
                return str(choices[0].get("text") or "")
    except Exception:
        pass
    return ""


def _extract_bedrock_converse_text(body_obj: Any) -> str:
    try:
        if not isinstance(body_obj, dict):
            return ""
        out = body_obj.get("output") or {}
        msg = out.get("message") or {}
        content = msg.get("content") or []
        if not isinstance(content, list):
            return ""
        parts = []
        for item in content:
            if isinstance(item, dict) and "text" in item:
                parts.append(str(item.get("text") or ""))
        return "".join(parts)
    except Exception:
        return ""


class LlmClient:
    """
    Provider-neutral text completion interface for LLM2.

    Reads only takctl.conf + secrets.conf.
    """

    def __init__(self) -> None:
        cfg = load_config()
        sec = load_secrets()

        self.provider = _s(cfg.llm_provider).lower()
        self.timeout_s = _safe_int(cfg.llm_timeout_s, 900)

        self.model = _s(cfg.llm_model)
        self.url = _s(cfg.llm_url)

        self.aws_region = _s(cfg.aws_region)
        self.bedrock_model_id = _s(cfg.bedrock_model_id)
        self.bedrock_api_key = _s(sec.bedrock_api_key)

    def complete_text(
        self,
        *,
        prompt: str,
        temperature: float,
        max_tokens: int,
        seed: Optional[int] = None,
        purpose: str = "",
    ) -> Dict[str, Any]:
        started = _now_iso()
        t0 = time.time()

        out: Dict[str, Any] = {
            "ok": False,
            "provider": self.provider,
            "model": "",
            "url": "",
            "text": "",
            "http_status": 0,
            "body_bytes": 0,
            "error": None,
            "started_at": started,
            "purpose": _s(purpose),
            "usage": {
                "input_tokens": None,
                "output_tokens": None,
                "total_tokens": None,
            },
        }

        body_obj: Any = {}
        req_payload: Dict[str, Any] = {}

        try:
            if self.provider == "bedrock":
                if not self.aws_region:
                    raise RuntimeError("missing aws_region in takctl.conf for bedrock")
                if not self.bedrock_model_id:
                    raise RuntimeError("missing bedrock_model_id in takctl.conf for bedrock")
                if not self.bedrock_api_key:
                    raise RuntimeError("missing bedrock_api_key in secrets.conf for bedrock")

                model_id = _normalize_bedrock_model_id(self.bedrock_model_id, self.aws_region)

                url = f"https://bedrock-runtime.{self.aws_region}.amazonaws.com/model/{model_id}/converse"
                payload: Dict[str, Any] = {
                    "messages": [{"role": "user", "content": [{"text": str(prompt or "")}]}],
                    "inferenceConfig": {
                        "temperature": float(temperature),
                        "maxTokens": int(max_tokens),
                    },
                }
                req_payload = payload
                headers = {"Authorization": f"Bearer {self.bedrock_api_key}"}
                status, body = _http_post_json(url, payload, timeout_s=self.timeout_s, headers=headers)

                out["model"] = model_id
                out["url"] = url
                out["http_status"] = status
                out["body_bytes"] = len(body)

                body_text = body.decode("utf-8", errors="replace")
                try:
                    body_obj = json.loads(body_text or "{}")
                except Exception:
                    body_obj = {"_raw": body_text}

                if status >= 400:
                    out["ok"] = False
                    out["error"] = f"Bedrock HTTP {status}: {body_text[:800]}"
                else:
                    out["text"] = _extract_bedrock_converse_text(body_obj)
                    out["ok"] = True

            elif self.provider == "local":
                payload2: Dict[str, Any] = {
                    "model": self.model,
                    "prompt": str(prompt or ""),
                    "temperature": float(temperature),
                    "n_predict": int(max_tokens),
                    "max_tokens": int(max_tokens),
                }
                if seed is not None:
                    payload2["seed"] = int(seed)

                req_payload = payload2
                status, body = _http_post_json(self.url, payload2, timeout_s=self.timeout_s)

                out["model"] = self.model
                out["url"] = self.url
                out["http_status"] = status
                out["body_bytes"] = len(body)

                body_text = body.decode("utf-8", errors="replace")
                try:
                    body_obj = json.loads(body_text or "{}")
                except Exception:
                    body_obj = {"_raw": body_text}

                if status >= 400:
                    out["ok"] = False
                    out["error"] = f"Local LLM HTTP {status}: {body_text[:800]}"
                else:
                    out["text"] = _extract_openai_completions_text(body_obj)
                    out["ok"] = True

            else:
                raise RuntimeError(f"invalid llm_provider in takctl.conf: {self.provider!r}")

        except Exception as e:
            out["ok"] = False
            out["error"] = f"{type(e).__name__}: {e}"

        out["elapsed_ms"] = int((time.time() - t0) * 1000)
        out["usage"] = _extract_usage_fields(self.provider, body_obj)

        _append_usage_log({
            "ts_utc": _now_iso(),
            "started_at": started,
            "provider": out.get("provider"),
            "model": out.get("model"),
            "purpose": out.get("purpose") or "",
            "ok": bool(out.get("ok")),
            "http_status": out.get("http_status"),
            "elapsed_ms": out.get("elapsed_ms"),
            "prompt_chars": len(str(prompt or "")),
            "response_chars": len(str(out.get("text") or "")),
            "max_tokens_requested": int(max_tokens),
            "temperature": float(temperature),
            "seed": seed,
            "input_tokens": (out.get("usage") or {}).get("input_tokens"),
            "output_tokens": (out.get("usage") or {}).get("output_tokens"),
            "total_tokens": (out.get("usage") or {}).get("total_tokens"),
            "url": out.get("url"),
            "error": out.get("error"),
        })

        return out
