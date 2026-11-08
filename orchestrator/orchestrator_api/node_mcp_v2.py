"""Authenticated MCP JSON-RPC bridge to a registered TAK node.

This is a narrow JSON request/response bridge, not a full streaming MCP proxy.
Node-side endpoints are a separate deployment dependency.
"""
import json
import os
from pathlib import Path
import re
import ssl
import urllib.error
import urllib.request

from fastapi import APIRouter, HTTPException, Request
from orchestrator_core.config import load_orch_config
from orchestrator_core.nodes_state import get_node
from orchestrator_core.units_state import ensure_unit_orchestrator_secret
from .api_v2 import require_operator
from .service_auth import service_auth_ok

router = APIRouter(prefix="/api/v2")
NODE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
FQDN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$")
DOMAINS = {"devops", "taks"}
METHODS = {"tools/list", "tools/call"}
MAX_REQUEST = 65536
MAX_RESPONSE = 1048576


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@router.post("/nodes/{node_id}/mcp/{domain}")
async def node_mcp(node_id: str, domain: str, request: Request):
    require_operator(request)
    if not NODE_ID.fullmatch(node_id) or domain not in DOMAINS:
        raise HTTPException(status_code=400, detail="Invalid node or MCP domain")
    if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
        raise HTTPException(status_code=415, detail="JSON required")
    if request.headers.get("content-length", "").isdigit() and int(request.headers["content-length"]) > MAX_REQUEST:
        raise HTTPException(status_code=413, detail="MCP request too large")
    body = await request.body()
    if len(body) > MAX_REQUEST:
        raise HTTPException(status_code=413, detail="MCP request too large")
    try:
        message = json.loads(body)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or "id" not in message:
        raise HTTPException(status_code=400, detail="Invalid JSON-RPC request")
    method = message.get("method")
    if method not in METHODS:
        raise HTTPException(status_code=403, detail="MCP method not allowed")
    params = message.get("params", {})
    if not isinstance(params, dict):
        raise HTTPException(status_code=400, detail="Invalid MCP parameters")
    # Service-token callers may only invoke the explicitly enumerated
    # read-only diagnostics below. This is NOT a general remote shell proxy.
    if service_auth_ok(request):
        safe_tools = {
            "host_identity", "host_resources", "listening_ports",
            "service_list", "service_status", "service_logs",
            "nginx_check", "cert_status", "file_stat", "installer_tail",
        }
        if domain != "devops":
            raise HTTPException(status_code=403, detail="Service MCP domain not allowed")
        if method == "tools/call" and (
            params.get("name") not in safe_tools or
            not isinstance(params.get("arguments", {}), dict)
        ):
            raise HTTPException(status_code=403, detail="Service MCP tool not allowed")
    if method == "tools/call":
        name = params.get("name")
        if not isinstance(name, str) or not name:
            raise HTTPException(status_code=400, detail="Tool name required")
        # The node enforces its own per-domain tool authorization. Do not
        # expose this route to MCP service tokens without an explicit tool ACL.
    record = get_node(node_id)
    if not isinstance(record, dict) or not record:
        raise HTTPException(status_code=404, detail="Unknown node")
    fqdn = str(record.get("fqdn") or "")
    unit = str(record.get("unit_path") or record.get("unit") or "")
    if not FQDN.fullmatch(fqdn) or "." not in fqdn or ".." in fqdn or not unit:
        raise HTTPException(status_code=400, detail="Node registry incomplete")
    secret = ensure_unit_orchestrator_secret(unit)
    if not secret:
        raise HTTPException(status_code=503, detail="Node credential unavailable")
    if domain == "devops":
        # Separate SNI hostname, private CA and client identity. The public
        # Let's Encrypt certificate is never consulted for DevOps requests.
        ca = os.environ.get("TAKS_DEVOPS_CA_CERT", str(Path(load_orch_config().paths.state_dir) / "devops-pki" / "ca.crt"))
        cert = os.environ.get("TAKS_DEVOPS_CLIENT_CERT", str(Path(load_orch_config().paths.state_dir) / "devops-pki" / "client.crt"))
        key = os.environ.get("TAKS_DEVOPS_CLIENT_KEY", str(Path(load_orch_config().paths.state_dir) / "devops-pki" / "client.key"))
        try:
            context = ssl.create_default_context(cafile=ca)
            context.load_cert_chain(certfile=cert, keyfile=key)
        except (OSError, ssl.SSLError) as exc:
            raise HTTPException(status_code=503, detail="DevOps mTLS credentials unavailable") from exc
        url = "https://devops." + fqdn + "/api/orchestrator/mcp/devops"
    else:
        context = ssl.create_default_context()
        url = "https://" + fqdn + "/api/orchestrator/mcp/taks"
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Authorization": "Bearer " + secret,
                 "Content-Type": "application/json",
                 "Accept": "application/json"},
    )
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=context),
        NoRedirect(),
    )
    try:
        with opener.open(req, timeout=20) as response:
            if response.headers.get_content_type() != "application/json":
                raise HTTPException(status_code=502, detail="Unexpected node MCP response type")
            raw = response.read(MAX_RESPONSE + 1)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
        raise HTTPException(status_code=502, detail="Node MCP unavailable") from exc
    if len(raw) > MAX_RESPONSE:
        raise HTTPException(status_code=502, detail="Node MCP response too large")
    try:
        result = json.loads(raw)
    except ValueError:
        raise HTTPException(status_code=502, detail="Invalid node MCP response")
    if not isinstance(result, dict) or result.get("jsonrpc") != "2.0" or result.get("id") != message["id"]:
        raise HTTPException(status_code=502, detail="Invalid node JSON-RPC response")
    return result
