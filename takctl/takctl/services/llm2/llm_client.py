from __future__ import annotations

import json
import os
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _safe_int(v: Any, default: int) -> int:
    try:
        return int(v)
    except Exception:
        return default


def _s(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _read_env_file(path: Path) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not path.exists():
        return out
    try:
        for ln in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = ln.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip()
            if k:
                out[k] = v
    except Exception:
        # best-effort; keep empty
        return out
    return out


def _pick(k: str, file_kv: Dict[str, str], default: str = "") -> str:
    # precedence: llm.env -> process env -> default
    return _s(file_kv.get(k) or os.environ.get(k) or default)


def _bedrock_geo_prefix(region: str) -> str:
    """
    Bedrock API key method uses a geography prefix in the model identifier
    (AWS examples show 'us.' prefix). For eu-north-1 this should be 'eu.'.
    """
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
    # fallback: no prefix (may still fail, but we won't guess wrong)
    return ""


def _normalize_bedrock_model_id(model_id: str, region: str) -> str:
    mid = _s(model_id)
    if not mid:
        return ""
    # If already prefixed like "eu.anthropic...." keep it
    if len(mid) > 3 and mid[2] == ".":
        # "us." / "eu." / "ap." etc
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
        # Important: preserve body for debugging
        try:
            body = e.read() or b""
        except Exception:
            body = b""
        return int(getattr(e, "code", 0) or 0), body


def _extract_openai_completions_text(body_obj: Any) -> str:
    # llama.cpp /v1/completions compatible: {"choices":[{"text":"..."}]}
    try:
        if isinstance(body_obj, dict):
            choices = body_obj.get("choices") or []
            if choices and isinstance(choices[0], dict):
                return str(choices[0].get("text") or "")
    except Exception:
        pass
    return ""


def _extract_bedrock_converse_text(body_obj: Any) -> str:
    # Bedrock converse: output.message.content[] items can contain {"text": "..."}
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

    IMPORTANT: This client reads /opt/tak/tools/takctl/secrets/llm.env
    (same file the WebUI writes) and overlays it on top of process env.
    """

    def __init__(self, env_path: Optional[str] = None) -> None:
        self.env_path = _s(env_path) or _s(os.environ.get("TAKCTL_LLM_ENV_PATH")) or "/opt/tak/tools/takctl/secrets/llm.env"
        self._env_kv = _read_env_file(Path(self.env_path))

        self.provider = _pick("TAKCTL_LLM_PROVIDER", self._env_kv, "local").lower()

        # shared knobs
        self.timeout_s = _safe_int(_pick("TAKCTL_LLM_TIMEOUT_S", self._env_kv, "900"), 900)

        # local
        self.model = _pick("TAKCTL_LLM_MODEL", self._env_kv, "local-small")
        self.url = _pick("TAKCTL_LLM_URL", self._env_kv, "http://127.0.0.1:8090/v1/completions")

        # bedrock
        self.aws_region = _pick("TAKCTL_AWS_REGION", self._env_kv, _pick("AWS_REGION", self._env_kv, ""))
        self.bedrock_model_id = _pick("TAKCTL_BEDROCK_MODEL_ID", self._env_kv, "")
        self.bedrock_api_key = _pick("AWS_BEARER_TOKEN_BEDROCK", self._env_kv, "")

    def complete_text(
        self,
        *,
        prompt: str,
        temperature: float,
        max_tokens: int,
        seed: Optional[int] = None,
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
        }

        try:
            if self.provider == "bedrock":
                if not self.aws_region:
                    raise RuntimeError("missing TAKCTL_AWS_REGION (or AWS_REGION) for bedrock")
                if not self.bedrock_model_id:
                    raise RuntimeError("missing TAKCTL_BEDROCK_MODEL_ID for bedrock")
                if not self.bedrock_api_key:
                    raise RuntimeError("missing AWS_BEARER_TOKEN_BEDROCK for bedrock API key auth")

                # API-key Bedrock uses geography-prefixed model id (e.g. us.anthropic..., eu.anthropic...) :contentReference[oaicite:1]{index=1}
                model_id = _normalize_bedrock_model_id(self.bedrock_model_id, self.aws_region)

                url = f"https://bedrock-runtime.{self.aws_region}.amazonaws.com/model/{model_id}/converse"
                payload: Dict[str, Any] = {
                    "messages": [{"role": "user", "content": [{"text": str(prompt or "")}]}],
                    "inferenceConfig": {
                        "temperature": float(temperature),
                        "maxTokens": int(max_tokens),
                    },
                }
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
                    # show actual Bedrock error body
                    out["ok"] = False
                    out["error"] = f"Bedrock HTTP {status}: {body_text[:800]}"
                else:
                    out["text"] = _extract_bedrock_converse_text(body_obj)
                    out["ok"] = True

            else:
                # local llama.cpp (OpenAI-ish /v1/completions)
                payload2: Dict[str, Any] = {
                    "model": self.model,
                    "prompt": str(prompt or ""),
                    "temperature": float(temperature),
                    # llama.cpp typically uses n_predict; also include max_tokens for compatibility
                    "n_predict": int(max_tokens),
                    "max_tokens": int(max_tokens),
                }
                if seed is not None:
                    payload2["seed"] = int(seed)

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

        except Exception as e:
            out["ok"] = False
            out["error"] = f"{type(e).__name__}: {e}"

        out["ended_at"] = _now_iso()
        out["elapsed_ms"] = int((time.time() - t0) * 1000)
        return out

