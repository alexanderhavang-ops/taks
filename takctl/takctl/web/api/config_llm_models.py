from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(tags=["config"])

ENV_PATH = Path("/opt/tak/tools/takctl/secrets/llm.env")


def _read_env_file(path: Path) -> Dict[str, str]:
    out: Dict[str, str] = {}
    try:
        if not path.exists():
            return out
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = (raw or "").strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = (k or "").strip()
            v = (v or "").strip()
            if k:
                out[k] = v
    except Exception:
        return out
    return out


def _write_env_file(path: Path, kv: Dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: List[str] = []
    for k in sorted(kv.keys()):
        v = kv[k]
        lines.append(f"{k}={v}")
    tmp = path.with_suffix(".tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass


def _overlay_env() -> Dict[str, str]:
    """
    Merge current process env + secrets/llm.env (file overrides process),
    and return the merged mapping.
    """
    merged = dict(os.environ)
    file_kv = _read_env_file(ENV_PATH)
    merged.update(file_kv)
    return {k: str(v) for k, v in merged.items()}


def _catalog(provider: str) -> List[Dict[str, str]]:
    """
    Keep this small and pragmatic. You can expand later.
    IDs must match what your provider expects:
      - local: llama.cpp alias names (e.g. local-small)
      - bedrock: Bedrock modelId (e.g. anthropic.claude-3-5-sonnet-20240620-v1:0)
    """
    p = (provider or "").strip().lower()

    if p == "bedrock":
        return [
            # Claude (strong generalist)
            {"id": "anthropic.claude-3-5-sonnet-20240620-v1:0", "label": "Claude 3.5 Sonnet"},
            {"id": "anthropic.claude-3-5-haiku-20241022-v1:0", "label": "Claude 3.5 Haiku"},
            # Titan Text (AWS)
            {"id": "amazon.titan-text-premier-v1:0", "label": "Titan Text Premier"},
            {"id": "amazon.titan-text-express-v1", "label": "Titan Text Express"},
            # Llama (if enabled in your account/region)
            {"id": "meta.llama3-70b-instruct-v1:0", "label": "Llama 3 70B Instruct"},
            {"id": "meta.llama3-8b-instruct-v1:0", "label": "Llama 3 8B Instruct"},
            # Mistral (if enabled)
            {"id": "mistral.mistral-large-2402-v1:0", "label": "Mistral Large"},
            {"id": "mistral.mistral-small-2402-v1:0", "label": "Mistral Small"},
        ]

    # local (llama.cpp aliases) — keep whatever you run as a selectable option
    return [
        {"id": "local-small", "label": "Local (llama.cpp) — local-small"},
    ]


@router.get("/api/config/llm/models")
def get_llm_models(request: Request, provider: Optional[str] = None) -> Dict[str, Any]:
    env = _overlay_env()
    active_provider = (provider or env.get("TAKCTL_LLM_PROVIDER") or "local").strip().lower()
    items = _catalog(active_provider)
    return {
        "ok": True,
        "provider": active_provider,
        "models": items,
    }


class SetModelReq(BaseModel):
    provider: str
    model_id: str


@router.post("/api/config/llm/model")
def set_llm_model(req: SetModelReq) -> Dict[str, Any]:
    provider = (req.provider or "").strip().lower()
    model_id = (req.model_id or "").strip()

    if provider not in ("local", "bedrock"):
        raise HTTPException(status_code=400, detail="bad provider")

    allowed = {m["id"] for m in _catalog(provider)}
    if model_id not in allowed:
        raise HTTPException(status_code=400, detail="model_id not in catalog for provider")

    kv = _read_env_file(ENV_PATH)

    # Persist provider + model selection
    kv["TAKCTL_LLM_PROVIDER"] = provider
    if provider == "bedrock":
        kv["TAKCTL_BEDROCK_MODEL_ID"] = model_id
    else:
        kv["TAKCTL_LLM_MODEL"] = model_id

    _write_env_file(ENV_PATH, kv)

    # Apply to current process env too (so changes take effect immediately in-process)
    os.environ["TAKCTL_LLM_PROVIDER"] = provider
    if provider == "bedrock":
        os.environ["TAKCTL_BEDROCK_MODEL_ID"] = model_id
    else:
        os.environ["TAKCTL_LLM_MODEL"] = model_id

    return {"ok": True, "provider": provider, "model_id": model_id, "env_path": str(ENV_PATH)}
