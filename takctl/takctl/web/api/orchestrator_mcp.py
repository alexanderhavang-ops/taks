"""Node MCP tool endpoint mounted in the existing TAKCTL web service.

Only read-only local diagnostics are exposed in this first vertical slice.
No shell, arbitrary filesystem access, or second listener is introduced.
"""
import json
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from takctl.web.api.orchestrator import require_orchestrator_secret

router = APIRouter(prefix="/api/orchestrator", tags=["orchestrator-mcp"])
MAX_BODY = 65536
from takctl.web.mcp_domains import devops, taks

DOMAINS = {"devops": devops, "taks": taks}

def _run_tool(domain: str, name: str, args: dict) -> dict:
    module = DOMAINS[domain]
    if name not in {tool["name"] for tool in module.TOOLS}:
        raise HTTPException(status_code=403, detail="Tool not allowed in domain")
    try:
        return module.call(name, args)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/mcp/{domain}")
async def node_mcp(domain: str, request: Request):
    require_orchestrator_secret(request)
    if domain not in DOMAINS:
        raise HTTPException(status_code=404, detail="Unknown MCP domain")
    if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
        raise HTTPException(status_code=415, detail="JSON required")
    if request.headers.get("content-length", "").isdigit() and int(request.headers["content-length"]) > MAX_BODY:
        raise HTTPException(status_code=413, detail="Request too large")
    raw = await request.body()
    if len(raw) > MAX_BODY:
        raise HTTPException(status_code=413, detail="Request too large")
    try:
        message = json.loads(raw)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or "id" not in message:
        raise HTTPException(status_code=400, detail="Invalid JSON-RPC")
    params = message.get("params", {})
    if not isinstance(params, dict):
        raise HTTPException(status_code=400, detail="Invalid params")
    method = message.get("method")
    if method == "tools/list":
        result = {"tools": DOMAINS[domain].TOOLS}
    elif method == "tools/call":
        name, args = params.get("name"), params.get("arguments", {})
        if not isinstance(name, str) or not isinstance(args, dict):
            raise HTTPException(status_code=400, detail="Invalid tool call")
        # Tools may call this same single-worker ASGI server over loopback.
        # Keep its event loop free to serve those requests.
        result = await run_in_threadpool(_run_tool, domain, name, args)
    else:
        raise HTTPException(status_code=403, detail="Unsupported MCP method")
    return {"jsonrpc": "2.0", "id": message["id"], "result": result}
