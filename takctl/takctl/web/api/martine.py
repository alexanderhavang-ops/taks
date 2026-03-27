from __future__ import annotations

from typing import Any, Dict
import sys
from pathlib import Path
import asyncio

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api/martine", tags=["martine"])


def _load_run_once():
    """
    Load Martine from runtime, not source.
    """
    candidates = [
        Path("/opt/tak/tools/martine"),
    ]

    for p in candidates:
        s = str(p)
        if p.exists() and s not in sys.path:
            sys.path.insert(0, s)

    try:
        from martine.agent.simple_agent import run_once  # type: ignore
        return run_once
    except Exception as e:
        raise RuntimeError(f"unable to import Martine runtime: {type(e).__name__}: {e}")


@router.get("/health")
async def martine_health() -> Dict[str, Any]:
    return {"ok": True, "name": "martine"}


@router.post("/ask")
async def martine_ask(req: Request) -> Dict[str, Any]:
    try:
        body = await req.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid json body")

    question = ""
    if isinstance(body, dict):
        question = str(body.get("question") or "").strip()

    if not question:
        raise HTTPException(status_code=400, detail="missing question")

    try:
        run_once = _load_run_once()
        result = await asyncio.to_thread(run_once, question)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"martine ask failed: {type(e).__name__}: {e}")
