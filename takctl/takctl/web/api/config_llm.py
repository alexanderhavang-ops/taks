from __future__ import annotations

import os
from fastapi import APIRouter, HTTPException, Request
from typing import Any, Dict, Optional

from takctl.services.llm2.model_catalog import list_models
from takctl.services.llm2.llm_env import read_llm_env, write_llm_env, redact_config

router = APIRouter()


@router.get("/api/config/llm/models")
def api_llm_models(provider: str = "local"):
    prov = (provider or "local").strip().lower()
    if prov not in ("local", "bedrock"):
        raise HTTPException(status_code=400, detail="bad provider")
    return {"ok": True, "provider": prov, "models": list_models(prov)}


@router.get("/api/config/llm")
def api_llm_config():
    cfg = read_llm_env()
    out = redact_config(cfg)
    # convenience: also include available_models for current provider
    prov = (out.get("provider") or "local").strip().lower()
    out["available_models"] = list_models(prov)
    return out


@router.post("/api/config/llm")
async def api_llm_config_save(req: Request):
    body = await req.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="bad json")

    cfg = read_llm_env()

    provider = str(body.get("provider") or cfg.get("TAKCTL_LLM_PROVIDER") or "local").strip().lower()
    if provider not in ("local", "bedrock"):
        raise HTTPException(status_code=400, detail="bad provider")

    # set provider
    cfg["TAKCTL_LLM_PROVIDER"] = provider

    # shared knobs
    phase3_mode = str(body.get("phase3_mode") or "").strip().lower()
    if phase3_mode:
        cfg["TAKCTL_LLM2_PHASE3_MODE"] = phase3_mode

    # local config
    local_url = str(body.get("local_url") or "").strip()
    if local_url:
        cfg["TAKCTL_LLM_URL"] = local_url

    local_model = str(body.get("local_model") or "").strip()
    if local_model:
        cfg["TAKCTL_LLM_MODEL"] = local_model

    # bedrock config
    bedrock_region = str(body.get("bedrock_region") or "").strip()
    if bedrock_region:
        cfg["TAKCTL_AWS_REGION"] = bedrock_region

    bedrock_model_id = str(body.get("bedrock_model_id") or "").strip()
    if bedrock_model_id:
        cfg["TAKCTL_BEDROCK_MODEL_ID"] = bedrock_model_id

    # bedrock key: allow setting, but never return it; empty means "no change"
    bedrock_key = str(body.get("bedrock_key") or "").strip()
    if bedrock_key:
        cfg["AWS_BEARER_TOKEN_BEDROCK"] = bedrock_key

    write_llm_env(cfg)
    return {"ok": True, "env_path": cfg.get("__env_path__", "")}


@router.post("/api/config/llm/clear_key")
def api_llm_config_clear_key():
    cfg = read_llm_env()
    if "AWS_BEARER_TOKEN_BEDROCK" in cfg:
        cfg["AWS_BEARER_TOKEN_BEDROCK"] = ""
    write_llm_env(cfg)
    return {"ok": True, "env_path": cfg.get("__env_path__", "")}


@router.post("/api/config/llm/set_model")
async def api_llm_set_model(req: Request):
    """
    Convenience endpoint: set the model for a given provider.
    Body: { provider: "local|bedrock", model_id: "..." }
    """
    body = await req.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="bad json")

    provider = str(body.get("provider") or "local").strip().lower()
    model_id = str(body.get("model_id") or "").strip()
    if provider not in ("local", "bedrock"):
        raise HTTPException(status_code=400, detail="bad provider")
    if not model_id:
        raise HTTPException(status_code=400, detail="missing model_id")

    cfg = read_llm_env()
    cfg["TAKCTL_LLM_PROVIDER"] = provider
    if provider == "bedrock":
        cfg["TAKCTL_BEDROCK_MODEL_ID"] = model_id
    else:
        cfg["TAKCTL_LLM_MODEL"] = model_id

    write_llm_env(cfg)
    return {"ok": True, "provider": provider, "model_id": model_id, "env_path": cfg.get("__env_path__", "")}
