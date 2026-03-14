from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request

from takctl.services.llm2.model_catalog import list_models

router = APIRouter(prefix="/api/config", tags=["config"])

LLM_ENV_PATH = Path("/opt/tak/tools/takctl/secrets/llm.env")

_ALLOWED_KEYS = {
    "TAKCTL_LLM_PROVIDER",
    "TAKCTL_LLM_URL",
    "TAKCTL_LLM_MODEL",
    "TAKCTL_AWS_REGION",
    "TAKCTL_BEDROCK_MODEL_ID",
    "AWS_BEARER_TOKEN_BEDROCK",
    "TAKCTL_LLM2_PHASE3_MODE",
}


def _s(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _read_env_file(path: Path) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not path.exists():
        return out
    for ln in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = ln.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip()
        if not k:
            continue
        out[k] = v
    return out


def _uid(name: str) -> int:
    import pwd
    return pwd.getpwnam(name).pw_uid


def _gid(name: str) -> int:
    import grp
    return grp.getgrnam(name).gr_gid


def _write_env_file_atomic(path: Path, kv: Dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    lines = []
    lines.append("# LLM routing/config (installer-owned).")
    lines.append("# NOTE: key is stored here but never returned by the API/UI.")
    for k in sorted(_ALLOWED_KEYS):
        if k not in kv:
            continue
        v = kv.get(k, "")
        lines.append(f"{k}={v}")
    content = "\n".join(lines).rstrip() + "\n"

    tmp = path.with_suffix(".env.tmp")
    tmp.write_text(content, encoding="utf-8")

    os.chmod(tmp, 0o640)
    try:
        os.chown(tmp, _uid("tak"), _gid("tak"))
    except Exception:
        pass

    tmp.replace(path)


def _pick_effective(kv_file: Dict[str, str], key: str, default: str = "") -> str:
    return _s(kv_file.get(key) or os.environ.get(key) or default)


def _effective_env(*, provider_hint: str | None = None) -> Dict[str, Any]:
    kv = _read_env_file(LLM_ENV_PATH)

    provider = _pick_effective(kv, "TAKCTL_LLM_PROVIDER", "local").lower() or "local"
    local_url = _pick_effective(kv, "TAKCTL_LLM_URL", "http://127.0.0.1:8090/v1/completions")
    bedrock_region = _pick_effective(kv, "TAKCTL_AWS_REGION", _pick_effective(kv, "AWS_REGION", ""))
    bedrock_model_id = _pick_effective(kv, "TAKCTL_BEDROCK_MODEL_ID", "")
    bedrock_key_set = bool(_pick_effective(kv, "AWS_BEARER_TOKEN_BEDROCK", ""))

    # local model (with pollution protection)
    local_models = list_models("local")
    local_ids = {m.get("id") for m in local_models if isinstance(m, dict)}
    local_model = _pick_effective(kv, "TAKCTL_LLM_MODEL", "local-small") or "local-small"
    if local_model not in local_ids:
        # Someone wrote a Bedrock id into local_model — normalize view back to local-small
        local_model = "local-small"

    # provider-neutral active model_id
    model_id = local_model if provider == "local" else bedrock_model_id

    # provider hint only affects the models list returned to the UI
    mp = (provider_hint or provider).strip().lower()
    if mp not in ("local", "bedrock"):
        mp = provider
    available_models = list_models(mp)

    phase3_mode = _pick_effective(kv, "TAKCTL_LLM2_PHASE3_MODE", os.environ.get("TAKCTL_LLM2_PHASE3_MODE", "fallback")) or "fallback"

    return {
        "provider": provider,
        "model_id": model_id,
        "local_url": local_url,
        "local_model": local_model,
        "bedrock_region": bedrock_region,
        "bedrock_model_id": bedrock_model_id,
        "bedrock_key_set": bedrock_key_set,
        "phase3_mode": phase3_mode,
        "env_path": str(LLM_ENV_PATH),
        "available_models": available_models,
        "available_models_provider": mp,
    }


@router.get("/llm")
async def get_llm_config(provider: str | None = None) -> Dict[str, Any]:
    return _effective_env(provider_hint=provider)


@router.get("/llm/models")
async def get_llm_models(provider: str | None = None) -> Dict[str, Any]:
    prov = _s(provider or "local").lower()
    if prov not in ("local", "bedrock"):
        raise HTTPException(status_code=400, detail="provider must be local or bedrock")
    return {"ok": True, "provider": prov, "models": list_models(prov)}


@router.post("/llm")
async def set_llm_config(req: Request) -> Dict[str, Any]:
    try:
        body = await req.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid json body")

    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="invalid json body")

    kv = _read_env_file(LLM_ENV_PATH)

    # Provider first (so model routing uses the intended provider)
    if "provider" in body:
        kv["TAKCTL_LLM_PROVIDER"] = _s(body.get("provider")).lower()

    prov = _s(kv.get("TAKCTL_LLM_PROVIDER") or "local").lower() or "local"
    if prov not in ("local", "bedrock"):
        raise HTTPException(status_code=400, detail="provider must be local or bedrock")

    # Common knobs
    if "local_url" in body:
        kv["TAKCTL_LLM_URL"] = _s(body.get("local_url"))
    if "bedrock_region" in body:
        kv["TAKCTL_AWS_REGION"] = _s(body.get("bedrock_region"))
    if "phase3_mode" in body:
        kv["TAKCTL_LLM2_PHASE3_MODE"] = _s(body.get("phase3_mode"))

    # Provider-neutral model_id (THIS is what the UI should send)
    model_id = _s(body.get("model_id"))
    if model_id:
        if prov == "local":
            # Only accept valid local IDs (prevents bedrock ids poisoning local_model)
            local_ids = {m.get("id") for m in list_models("local") if isinstance(m, dict)}
            if model_id not in local_ids:
                raise HTTPException(status_code=400, detail="invalid local model_id")
            kv["TAKCTL_LLM_MODEL"] = model_id
        else:
            kv["TAKCTL_BEDROCK_MODEL_ID"] = model_id

    # Bedrock key handling
    clear_key = bool(body.get("clear_bedrock_key", False))
    new_key = _s(body.get("bedrock_api_key"))

    if clear_key:
        kv["AWS_BEARER_TOKEN_BEDROCK"] = ""
    elif new_key:
        kv["AWS_BEARER_TOKEN_BEDROCK"] = new_key

    _write_env_file_atomic(LLM_ENV_PATH, kv)
    return _effective_env()
