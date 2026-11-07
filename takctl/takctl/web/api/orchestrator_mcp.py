"""Node MCP tool endpoint mounted in the existing TAKCTL web service.

Only read-only local diagnostics are exposed in this first vertical slice.
No shell, arbitrary filesystem access, or second listener is introduced.
"""
import json
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from takctl.web.api.orchestrator import require_orchestrator_secret

router = APIRouter(prefix="/api/orchestrator", tags=["orchestrator-mcp"])
MAX_BODY = 65536
TOOL_SCHEMAS = {
    "devops": [
        {"name": "host_identity", "description": "Read the node hostname and OS release",
         "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
    ],
    "taks": [
        {"name": "runtime_status", "description": "Check local TAKCTL runtime availability",
         "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
    ],
}


def _run_tool(domain: str, name: str, args: dict) -> dict:
    allowed = {tool["name"] for tool in TOOL_SCHEMAS[domain]}
    if name not in allowed:
        raise HTTPException(status_code=403, detail="Tool not allowed in domain")
    if args:
        raise HTTPException(status_code=400, detail="Tool takes no arguments")
    if domain == "devops":
        os_release = Path("/etc/os-release")
        values = {}
        if os_release.is_file():
            for line in os_release.read_text(encoding="utf-8").splitlines():
                if line.startswith(("ID=", "VERSION_ID=", "PRETTY_NAME=")):
                    key, val = line.split("=", 1)
                    values[key] = val.strip('"')
        data = {"hostname": os.uname().nodename, "os": values}
    else:
        data = {"takctl_runtime": Path("/opt/tak/tools/takctl").is_dir(),
                "node_config": Path("/etc/taks/unit.json").is_file()}
    return {"content": [{"type": "text", "text": json.dumps(data, sort_keys=True)}]}


@router.post("/mcp/{domain}")
async def node_mcp(domain: str, request: Request):
    require_orchestrator_secret(request)
    if domain not in TOOL_SCHEMAS:
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
        result = {"tools": TOOL_SCHEMAS[domain]}
    elif method == "tools/call":
        name, args = params.get("name"), params.get("arguments", {})
        if not isinstance(name, str) or not isinstance(args, dict):
            raise HTTPException(status_code=400, detail="Invalid tool call")
        result = _run_tool(domain, name, args)
    else:
        raise HTTPException(status_code=403, detail="Unsupported MCP method")
    return {"jsonrpc": "2.0", "id": message["id"], "result": result}
