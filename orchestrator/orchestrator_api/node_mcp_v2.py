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
    # This bridge is callable via an authenticated loopback service token.
    # Delegate only reviewed node tools; discovery does not grant execution.
    # The node also validates each business tool and its confirmation flag.
    if service_auth_ok(request):
        safe_devops = {
            "host_identity", "host_resources", "listening_ports",
            "process_sample", "memory_read", "vmstat_sample",
            "service_list", "service_status", "service_logs",
            "nginx_check", "cert_status", "file_stat", "installer_tail",
            "java_processes", "takserver_logs", "takserver_readiness",
            "netstat_listeners", "lsof_tak_java",
        }
        safe_business = {
            "runtime_status", "api_surface", "takctl_health", "marti_diagnostics", "service_read", "service_write",
            "onboarding_user_create", "onboarding_send_invite", "product_health", "onboarding_diagnostics", "diagnostic_log", "diagnostic_file_stat", "network_capture_start", "network_capture_status",
        }
        safe_business.update({'get_reference_section', 'search_reference_docs', 'list_reference_doc_sections', 'get_reference_doc_context', 'search_reference_docs_semantic', 'simulation_read', 'list_reference_docs', 'simulation_control', 'map_read'})
        allowed = safe_devops if domain == "devops" else safe_business
        if method == "tools/call" and (
            params.get("name") not in allowed or
            not isinstance(params.get("arguments", {}), dict)
        ):
            raise HTTPException(status_code=403, detail="Service MCP tool not allowed")
    if method == "tools/call":
        name = params.get("name")
        if not isinstance(name, str) or not name:
            raise HTTPException(status_code=400, detail="Tool name required")
        # The node enforces its own per-domain tool authorization. Do not
        # expose this route to MCP service tokens without an explicit tool ACL.
    if method == "tools/call":
        from orchestrator_core.activity import store,instance_id
        record=get_node(node_id) or {}
        try:store().note_tool(node_id,instance_id(record),domain,params['name'],params.get('arguments',{}))
        except Exception as exc:raise HTTPException(status_code=503,detail="Activity audit unavailable; node tool not forwarded") from exc
    return forward_node_rpc(node_id,domain,message,body)


def forward_node_rpc(node_id,domain,message,body):
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
    except urllib.error.HTTPError as exc:
        if exc.code == 400:
            # Preserve bounded tool validation errors through the JSON-RPC
            # bridge; callers otherwise see only an unhelpful HTTPError.
            try:
                detail = json.loads(exc.read(2048)).get("detail")
            except (ValueError, TypeError, AttributeError):
                detail = None
            error = detail[:240] if isinstance(detail, str) else "Node tool rejected the request"
            return {"jsonrpc": "2.0", "id": message["id"], "result": {"isError": True,
                "content": [{"type": "text", "text": json.dumps({"ok": False, "error": error})}]}}
        raise HTTPException(status_code=502, detail="Node MCP unavailable") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
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


@router.post("/nodes/{node_id}/marti/diagnostics")
def marti_diagnostics(node_id: str, request: Request):
    """Read registered node Marti status with its installer TAK administrator."""
    require_operator(request)
    from orchestrator_core.marti_admin import diagnose
    return diagnose(node_id)


@router.post("/nodes/{node_id}/product-journal")
async def product_journal(node_id: str, request: Request):
    require_operator(request)
    if not NODE_ID.fullmatch(node_id):raise HTTPException(status_code=400,detail="Invalid node ID")
    data=await request.json()
    if not isinstance(data,dict) or set(data)!={'source','lines'} or data['source']!='takctl' or type(data['lines']) is not int or not 1<=data['lines']<=100:
        raise HTTPException(status_code=400,detail="Only bounded TAKCTL journal reads are supported")
    message={'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'service_logs','arguments':{'service':'takctl-web.service','lines':min(data['lines'],80)}}}
    return forward_node_rpc(node_id,'devops',message,json.dumps(message).encode())


@router.get("/nodes/{node_id}/activity")
def node_activity(node_id: str, request: Request):
    require_operator(request)
    from orchestrator_core.activity_observer import fresh_assessment
    record=get_node(node_id)
    if not record:raise HTTPException(status_code=404,detail="Unknown node")
    return {'ok':True,**fresh_assessment(record)}


@router.post("/activity/audit")
async def activity_audit(request: Request):
    require_operator(request)
    from orchestrator_core.activity import store,instance_id
    from orchestrator_core.nodes_state import list_nodes
    data=await request.json()
    if not isinstance(data,dict) or len(json.dumps(data))>2048:raise HTTPException(status_code=400,detail="Invalid audit marker")
    if data.get('component')=='devops':
        epoch=data.get('epoch','')
        if not isinstance(epoch,str) or not re.fullmatch(r'[a-f0-9]{32}',epoch):raise HTTPException(status_code=400,detail="Invalid audit epoch")
        store().component('devops',epoch);return {'ok':True}
    target=data.get('target');name=data.get('tool');operation=data.get('operation','')
    if not isinstance(target,str) or not NODE_ID.fullmatch(target) or not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9_]{1,100}',name) or not isinstance(operation,str) or len(operation)>80:
        raise HTTPException(status_code=400,detail="Invalid audit target or tool")
    records=[r for r in list_nodes() if target in (r.get('node_id'),r.get('fqdn'),r.get('unit_path')) and instance_id(r)]
    if not records:return {'ok':True,'recorded':False,'reason':'No current instance for target'}
    if len(records)!=1:raise HTTPException(status_code=409,detail="Ambiguous audit target")
    row=records[0];store().note_tool(row['node_id'],instance_id(row),'devops',name,{'operation':operation})
    return {'ok':True,'recorded':True}
