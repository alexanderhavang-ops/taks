"""Node-side MCP JSON-RPC endpoint factory.

The TAKCTL web application mounts this router with its existing orchestrator
bearer-token verifier. No new listener, token store or public access is created.
"""
from collections.abc import Callable
from fastapi import APIRouter, HTTPException, Request

MAX_BODY = 65536
DOMAINS = ("devops", "taks")


def create_node_mcp_router(
    *,
    verify_orchestrator: Callable[[Request], bool],
    list_tools: Callable[[str], list],
    call_tool: Callable[[str, str, dict], object],
) -> APIRouter:
    """Callbacks are provided by the existing TAKCTL authentication/tool layers.

    IMPORTANT: call_tool must enforce the node's own per-domain tool ACL.
    Do not mount until those callbacks are connected and tested.
    """
    router = APIRouter(prefix="/api/orchestrator")

    @router.post("/mcp/{domain}")
    async def handle_mcp(domain: str, request: Request):
        if not verify_orchestrator(request):
            raise HTTPException(status_code=401, detail="Unauthorized")
        if domain not in DOMAINS:
            raise HTTPException(status_code=404, detail="Unknown MCP domain")
        if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
            raise HTTPException(status_code=415, detail="JSON required")
        if request.headers.get("content-length", "").isdigit() and int(request.headers["content-length"]) > MAX_BODY:
            raise HTTPException(status_code=413, detail="Request too large")
        body = await request.body()
        if len(body) > MAX_BODY:
            raise HTTPException(status_code=413, detail="Request too large")
        try:
            import json
            message = json.loads(body)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid JSON")
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or "id" not in message:
            raise HTTPException(status_code=400, detail="Invalid JSON-RPC")
        method = message.get("method")
        params = message.get("params", {})
        if not isinstance(params, dict):
            raise HTTPException(status_code=400, detail="Invalid params")
        if method == "tools/list":
            result = {"tools": list_tools(domain)}
        elif method == "tools/call":
            name, args = params.get("name"), params.get("arguments", {})
            if not isinstance(name, str) or not name or not isinstance(args, dict):
                raise HTTPException(status_code=400, detail="Invalid tool call")
            # Tool authorization must be enforced inside the callback.
            result = call_tool(domain, name, args)
        else:
            raise HTTPException(status_code=403, detail="Unsupported MCP method")
        return {"jsonrpc": "2.0", "id": message["id"], "result": result}

    return router
