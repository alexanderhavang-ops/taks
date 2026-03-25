from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request

from takctl.config_store import apply_runtime_updates, runtime_public_state

router = APIRouter(prefix="/api/config", tags=["config"])


def _state() -> Dict[str, Any]:
    return runtime_public_state()


@router.get("")
async def get_config() -> Dict[str, Any]:
    return _state()


@router.get("/")
async def get_config_slash() -> Dict[str, Any]:
    return _state()


@router.post("")
async def set_config(req: Request) -> Dict[str, Any]:
    try:
        body = await req.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid JSON body")

    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="body must be a JSON object")

    config_updates = body.get("config_updates") or {}
    secret_updates = body.get("secret_updates") or {}

    if not isinstance(config_updates, dict):
        raise HTTPException(status_code=400, detail="config_updates must be an object")
    if not isinstance(secret_updates, dict):
        raise HTTPException(status_code=400, detail="secret_updates must be an object")

    try:
        apply_runtime_updates(
            config_updates=config_updates,
            secret_updates=secret_updates,
        )
        return _state()
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"failed to write config: {e}")


@router.post("/")
async def set_config_slash(req: Request) -> Dict[str, Any]:
    return await set_config(req)
