from __future__ import annotations

from typing import Any, Dict
import sys
from pathlib import Path
import asyncio

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

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

def _logs_root() -> Path:
    return Path("/opt/tak/tools/martine/state/logs")


@router.get("/runs/{run_id}/events")
async def martine_run_events(run_id: str) -> Dict[str, Any]:
    rid = str(run_id or "").strip()
    if not rid:
        raise HTTPException(status_code=400, detail="missing run_id")

    p = _logs_root() / rid / "events.jsonl"
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"events not found for run_id: {rid}")

    events = []
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            events.append(__import__("json").loads(line))
        except Exception:
            events.append({"type": "decode_error", "raw": line[:2000]})

    return {"ok": True, "run_id": rid, "events": events, "path": str(p)}


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
