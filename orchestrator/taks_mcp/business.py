"""TAKS business tools and scoped diagnostics, independent of DevOps MCP."""
import json
import re
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8090"
NODE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
UNIT = re.compile(r"^[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*$")


def call(method, path, data=None):
    try:
        from orchestrator_api.service_auth import business_service_token
        token = business_service_token()
        if not token:
            return {"ok": False, "error": "Service token unavailable"}
        headers = {"Authorization": "Bearer " + token, "Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(BASE + path, method=method, headers=headers,
                                         data=json.dumps(data).encode() if data is not None else None)
        timeout = 240 if path.endswith(("/launch", "/bundles/build", "/bundles/readiness")) else 25
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read(2_000_000))
    except (OSError, ValueError, urllib.error.URLError, TimeoutError) as exc:
        return {"ok": False, "error": type(exc).__name__}


def register_taks_tools(mcp, api_call=call, *, include_legacy_devops_tools=False):
    from taks_mcp.simulation import register_simulation_tools
    register_simulation_tools(mcp, api_call)
    original = mcp
    class BusinessCatalog:
        def tool(self, *args, **kwargs):
            register = original.tool(*args, **kwargs)
            def decorate(function):
                if not include_legacy_devops_tools and function.__name__ in {'taks_bundle_build','taks_bundle_readiness','taks_node_preview','taks_node_dry_run','taks_node_launch','taks_node_pause','taks_node_resume','taks_node_snooze','taks_node_wake','taks_node_shutdown','taks_node_devops_probe'}:
                    return function
                return register(function)
            return decorate
    mcp = BusinessCatalog()
    @mcp.tool()
    def taks_units_list() -> dict:
        """List TAKS organizational units."""
        return api_call("GET", "/api/v2/units")

    @mcp.tool()
    def taks_nodes_list() -> dict:
        """List TAK nodes and their product-level health."""
        return api_call("GET", "/api/v2/nodes")

    @mcp.tool()
    def taks_bundle_readiness(unit_path: str) -> dict:
        """Validate the complete TAKS bundle offline without booting a node."""
        if not UNIT.fullmatch(unit_path):
            return {"ok": False, "error": "Invalid unit path"}
        return api_call("POST", "/api/v2/bundles/readiness",
                        {"unit_path": unit_path, "role": "tak-node"})

    @mcp.tool()
    def taks_bundle_build(unit_path: str, confirm_build: bool = False) -> dict:
        """Create a validated bundle archive on the orchestrator; never starts EC2."""
        if not UNIT.fullmatch(unit_path):
            return {"ok": False, "error": "Invalid unit path"}
        if not confirm_build:
            return {"ok": False, "confirmation_required": True, "unit_path": unit_path}
        return api_call("POST", "/api/v2/bundles/build",
                        {"unit_path": unit_path, "role": "tak-node"})

    @mcp.tool()
    def taks_node_preview(unit_path: str, fqdn: str = "", instance_type: str = "") -> dict:
        """Preview a TAK node provisioning plan."""
        if not UNIT.fullmatch(unit_path):
            return {"ok": False, "error": "Invalid unit path"}
        if fqdn and not re.fullmatch(r"[A-Za-z0-9.-]+", fqdn):
            return {"ok": False, "error": "Invalid FQDN"}
        if instance_type and not re.fullmatch(r"[a-z0-9.]+", instance_type):
            return {"ok": False, "error": "Invalid instance type"}
        result = api_call("POST", "/api/v2/nodes/preview",
                          {"unit_path": unit_path, "role": "tak-node",
                           **({"fqdn": fqdn} if fqdn else {}),
                           **({"instance_type": instance_type} if instance_type else {})})
        return {"plan": result["plan"]} if isinstance(result, dict) and "plan" in result else result

    @mcp.tool()
    def taks_node_dry_run(unit_path: str, fqdn: str = "", instance_type: str = "") -> dict:
        """Validate TAK node provisioning through the orchestrator AWS dry-run."""
        preview = taks_node_preview(unit_path, fqdn, instance_type)
        if not isinstance(preview, dict) or preview.get("ok") is False:
            return preview
        return api_call("POST", "/api/v2/nodes/dry-run",
                        {"unit_path": unit_path, "role": "tak-node",
                         **({"fqdn": fqdn} if fqdn else {}),
                         **({"instance_type": instance_type} if instance_type else {})})

    @mcp.tool()
    def taks_node_devops_probe(node_id: str, operation: str = "tools/list",
                               service: str = "", lines: int = 40, path: str = "", file: str = "") -> dict:
        """Query a registered node's restricted read-only DevOps MCP over mTLS."""
        if not NODE_ID.fullmatch(node_id):
            return {"ok": False, "error": "Invalid node ID"}
        allowed = {
            "tools/list", "host_identity", "host_resources", "listening_ports",
            "service_list", "service_status", "service_logs",
            "nginx_check", "cert_status", "file_stat", "installer_tail",
            "java_processes", "takserver_logs", "takserver_readiness",
            "netstat_listeners", "lsof_tak_java",
        }
        if operation not in allowed:
            return {"ok": False, "error": "DevOps tool not allowed"}
        arguments = {}
        if operation in ("service_status", "service_logs"):
            if service not in (
                "takserver.service", "takctl-web.service", "nginx.service",
                "postgresql.service", "slapd.service", "mumble-server.service",
                "openfire.service", "martine-cot.service", "taks-heartbeat.timer",
            ):
                return {"ok": False, "error": "Service not allowlisted"}
            arguments["service"] = service
        if operation in ("service_logs", "installer_tail", "takserver_logs"):
            if type(lines) is not int or not 1 <= lines <= 80:
                return {"ok": False, "error": "Invalid line count"}
            arguments["lines"] = lines
        if operation == "takserver_logs":
            if file:
                if (len(file) > 128 or not re.fullmatch(r"[A-Za-z0-9_.-]+", file)
                        or file in (".", "..")):
                    return {"ok": False, "error": "Invalid log filename"}
                arguments["file"] = file
        if operation == "cert_status":
            if "." not in node_id:
                return {"ok": False, "error": "FQDN required"}
            arguments["fqdn"] = node_id
        if operation == "file_stat":
            if path not in (
                "/opt/tak/CoreConfig.xml", "/etc/nginx/nginx.conf",
                "/var/log/taks-installer-state.log",
                "/etc/taks-bootstrap.d/config.d/node.conf",
            ):
                return {"ok": False, "error": "Path not allowlisted"}
            arguments["path"] = path
        message = {"jsonrpc": "2.0", "id": 1,
                   "method": "tools/list" if operation == "tools/list" else "tools/call"}
        if operation != "tools/list":
            message["params"] = {"name": operation, "arguments": arguments}
        return api_call("POST", "/api/v2/nodes/" + node_id + "/mcp/devops", message)

    # User administration lives in the authenticated node Business MCP,
    # never in the host DevOps diagnostics.
    def business_call(node_id: str, tool: str, args: dict | None = None) -> dict:
        if not NODE_ID.fullmatch(node_id):
            return {"ok": False, "error": "Invalid node ID"}
        rpc = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"name": tool, "arguments": args or {}}}
        result = api_call("POST", "/api/v2/nodes/" + node_id + "/mcp/taks", rpc)
        if not isinstance(result, dict) or result.get("ok") is False:
            return result if isinstance(result, dict) else {"ok": False, "error": "Business MCP unavailable"}
        try:
            content = result["result"]["content"]
            payload = json.loads(next(p["text"] for p in content if p.get("type") == "text"))
            return payload if isinstance(payload, dict) else {"ok": False, "error": "Invalid Business MCP result"}
        except (KeyError, ValueError, TypeError, StopIteration):
            return {"ok": False, "error": "Invalid Business MCP response"}

    @mcp.tool()
    def taks_node_business_tools(node_id: str) -> dict:
        """List the tools actually installed on a node's authenticated Business MCP."""
        if not NODE_ID.fullmatch(node_id):
            return {"ok": False, "error": "Invalid node ID"}
        return api_call("POST", "/api/v2/nodes/" + node_id + "/mcp/taks",
                        {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})

    @mcp.tool()
    def taks_node_takctl_health(node_id: str) -> dict:
        """Check live TAKCTL health through the node Business MCP."""
        return business_call(node_id, "takctl_health")

    @mcp.tool()
    def taks_node_takctl_api_surface(node_id: str, path_prefix: str = "") -> dict:
        """Discover TAKCTL OpenAPI paths. Discovery does not authorize calls."""
        if not isinstance(path_prefix, str) or len(path_prefix) > 256 or (
            path_prefix and not path_prefix.startswith("/")
        ):
            return {"ok": False, "error": "Invalid path prefix"}
        return business_call(node_id, "api_surface", {"path_prefix": path_prefix})

    @mcp.tool()
    def taks_node_create_user(node_id: str, username: str, email: str,
                              callsign: str = "", group: str = "",
                              confirm_create: bool = False) -> dict:
        """Create a non-admin TAKCTL onboarding user on a node; explicit approval required."""
        if not confirm_create:
            return {"ok": False, "confirmation_required": True,
                    "node_id": node_id, "username": username}
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", username or ""):
            return {"ok": False, "error": "Invalid TAK username"}
        if not isinstance(email, str) or len(email) > 254 or not re.fullmatch(
            r"[^@\s]+@[^@\s]+\.[^@\s]+", email
        ):
            return {"ok": False, "error": "Invalid email"}
        return business_call(node_id, "onboarding_user_create", {
            "username": username, "email": email,
            "callsign": callsign, "group": group, "confirm_create": True})

    @mcp.tool()
    def taks_node_send_invite(node_id: str, username: str, email: str,
                              confirm_send: bool = False) -> dict:
        """Email an existing TAK user's one-time soldier card through TAKCTL."""
        if not confirm_send:
            return {"ok": False, "confirmation_required": True,
                    "node_id": node_id, "username": username}
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", username or ""):
            return {"ok": False, "error": "Invalid TAK username"}
        if not isinstance(email, str) or len(email) > 254 or not re.fullmatch(
            r"[^@\s]+@[^@\s]+\.[^@\s]+", email
        ):
            return {"ok": False, "error": "Invalid email"}
        return business_call(node_id, "onboarding_send_invite", {
            "username": username, "email": email, "confirm_send": True})

    @mcp.tool()
    def taks_node_service_read(node_id: str, service: str, operation: str, arguments: dict | None = None) -> dict:
        """Read service-native LDAP, Mumble Ice or Openfire REST diagnostics."""
        if service not in ("ldap", "mumble", "openfire", "simulation", "reference_docs", "activity"):
            return {"ok": False, "error": "Unsupported service"}
        if service=='activity' and operation in ('status','inactivity'):
            if not NODE_ID.fullmatch(node_id):return {'ok':False,'error':'Invalid node ID'}
            return api_call('GET','/api/v2/nodes/'+node_id+'/activity')
        return business_call(node_id, "service_read", {
            "service": service, "operation": operation, "arguments": arguments or {}})

    @mcp.tool()
    def taks_node_service_write(node_id: str, service: str, operation: str,
                               arguments: dict | None = None, confirm_write: bool = False) -> dict:
        """Change LDAP memberships, Mumble channels or Openfire rooms after confirmation."""
        if confirm_write is not True:
            return {"ok": False, "confirmation_required": True}
        if service not in ("ldap", "mumble", "openfire", "simulation", "reference_docs", "activity"):
            return {"ok": False, "error": "Unsupported service"}
        return business_call(node_id, "service_write", {
            "service": service, "operation": operation, "arguments": arguments or {}, "confirm_write": True})

    @mcp.tool()
    def taks_node_marti_diagnostics(node_id: str) -> dict:
        """Read live Marti sessions and enrollment status using the installer TAK admin."""
        if not NODE_ID.fullmatch(node_id):
            return {"ok": False, "error": "Invalid node ID"}
        return api_call("POST", "/api/v2/nodes/" + node_id + "/marti/diagnostics", {})

    @mcp.tool()
    def taks_node_network_capture_start(node_id: str, host_ip: str = '', ports: list[int] | None = None, seconds: int = 60, syn_only: bool = True) -> dict:
        """Start an admin-only metadata capture, at most 60 seconds. Omit host_ip to discover clients by SYNs on ports; then repeat with a discovered IP and syn_only=false. Poll capture_status."""
        return business_call(node_id,'network_capture_start',{'host_ip':host_ip,'ports':ports,'seconds':seconds,'syn_only':syn_only})

    @mcp.tool()
    def taks_node_network_capture_status(node_id: str, capture_id: str) -> dict:
        """Read bounded packet counts, SYN/SYN-ACK/reset evidence and discovered client IPs."""
        return business_call(node_id,'network_capture_status',{'capture_id':capture_id})

    @mcp.tool()
    def taks_node_diagnostic_log(node_id: str, source: str, lines: int = 40) -> dict:
        """Read a bounded, credential-redacted product log through Business MCP."""
        if source not in ('voice_auth','openfire','takctl','installer','business_tests','nginx') or type(lines) is not int or not 1 <= lines <= 100:
            return {'ok':False,'error':'Invalid log source or line limit'}
        if source == 'takctl':
            from taks_mcp.journal import takctl_journal
            return takctl_journal(api_call,node_id,lines)
        return business_call(node_id,'diagnostic_log',{'source':source,'lines':lines})

    @mcp.tool()
    def taks_node_diagnostic_file_stat(node_id: str, source: str) -> dict:
        """Read fixed product-log metadata, without file contents or arbitrary paths."""
        if source not in ('voice_auth','openfire','takctl','installer','business_tests','nginx'):
            return {'ok':False,'error':'Invalid diagnostic file'}
        if source == 'takctl':
            if not NODE_ID.fullmatch(node_id):return {'ok':False,'error':'Invalid node ID'}
            return {'ok':True,'source':'takctl','backend':'systemd_journal','file_available':False,'reason':'TAKCTL service logs are read through diagnostic_log from the systemd journal'}
        return business_call(node_id,'diagnostic_file_stat',{'source':source})

    @mcp.tool()
    def taks_node_onboarding_diagnostics(node_id: str, username: str) -> dict:
        """Read credential-free onboarding and device diagnostics as an operator."""
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}',username or ''):
            return {'ok':False,'error':'Invalid username'}
        return business_call(node_id,'onboarding_diagnostics',{'username':username})

    @mcp.tool()
    def taks_node_health(node_id: str) -> dict:
        """Return the TAKS product-health checks for a registered node."""
        if not NODE_ID.fullmatch(node_id):
            return {"ok": False, "error": "Invalid node ID"}
        inventory = api_call("GET", "/api/v2/nodes")
        if not isinstance(inventory, dict) or inventory.get("ok") is False:
            return {"ok": False, "error": "Inventory unavailable"}
        matches = [n for n in inventory.get("items", [])
                   if isinstance(n, dict) and n.get("node_id") == node_id]
        if len(matches) != 1:
            return {"ok": False, "error": "Node not uniquely registered"}
        node = matches[0]
        result = {"ok": True, "node_id": node_id, "aws_state": node.get("aws_state"),
                  "status": node.get("status"), "checks": node.get("checks", {})}
        # Include a narrow diagnostic while the client's tool catalog catches up.
        # Only probe an online running node; this never grants general tool execution.
        if node.get("aws_state") == "running" and node.get("status") == "online":
            path = '/api/v2/nodes/' + node_id + '/mcp/taks'
            result['marti_admin'] = taks_node_marti_diagnostics(node_id)
            # A non-mutating probe makes node Business MCP availability visible
            # in the existing health tool even before new plugin methods sync.
            business_listing = api_call(
                "POST", "/api/v2/nodes/" + node_id + "/mcp/taks",
                {"jsonrpc": "2.0", "id": 4, "method": "tools/list"})
            result["business_mcp"] = {
                "reachable": isinstance(business_listing, dict)
                and isinstance(business_listing.get("result"), dict),
                "tools": [
                    entry.get("name") for entry in
                    business_listing.get("result", {}).get("tools", [])
                    if isinstance(entry, dict)
                ] if isinstance(business_listing, dict) else [],
            }
            # Shared TAK Server troubleshooting belongs in Business health too.
            # It is read-only and contains no host-admin or client-management action.
            readiness = api_call(
                "POST", path,
                {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                 "params": {"name": "product_health", "arguments": {}}})
            if isinstance(readiness, dict) and isinstance(readiness.get("result"), dict):
                result["takserver_readiness"] = readiness["result"]
        return result

    @mcp.tool()
    def taks_node_launch(unit_path: str, confirm_launch: bool = False,
                         fqdn: str = "", instance_type: str = "") -> dict:
        """Provision a paid TAK node only after explicit confirmation."""
        if not confirm_launch:
            return {"ok": False, "confirmation_required": True}
        preview = taks_node_preview(unit_path, fqdn, instance_type)
        if not isinstance(preview, dict) or preview.get("ok") is False:
            return preview
        # The REST API enforces AWS-authoritative duplicate prevention.
        # Never treat an orphaned, terminated registry record as a live node.
        return api_call("POST", "/api/v2/nodes/launch",
                        {"unit_path": unit_path, "role": "tak-node",
                         **({"fqdn": fqdn} if fqdn else {}),
                         **({"instance_type": instance_type} if instance_type else {})})

    def lifecycle(node_id, action, confirmed):
        if not NODE_ID.fullmatch(node_id):
            return {"ok": False, "error": "Invalid node ID"}
        if not confirmed:
            return {"ok": False, "confirmation_required": True, "node_id": node_id, "action": action}
        inventory = api_call("GET", "/api/v2/nodes")
        if not isinstance(inventory, dict) or inventory.get("ok") is False:
            return {"ok": False, "error": "Inventory unavailable"}
        matches = [n for n in inventory.get("items", []) if isinstance(n, dict) and n.get("node_id") == node_id]
        if len(matches) != 1:
            return {"ok": False, "error": "Node not uniquely registered"}
        state = matches[0].get("aws_state")
        if state != ("running" if action == "pause" else "stopped"):
            return {"ok": False, "error": "Invalid lifecycle state", "aws_state": state}
        return api_call("POST", "/api/v2/nodes/" + node_id + "/" + action, {})

    @mcp.tool()
    def taks_node_pause(node_id: str, confirm_pause: bool = False) -> dict:
        """Pause node: stop EC2 while preserving instance identity and EBS data."""
        return lifecycle(node_id, "pause", confirm_pause)

    @mcp.tool()
    def taks_node_resume(node_id: str, confirm_resume: bool = False) -> dict:
        """Resume a paused node: start the same EC2 instance."""
        return lifecycle(node_id, "resume", confirm_resume)

    @mcp.tool()
    def taks_node_snooze(node_id: str, confirm_snooze: bool = False) -> dict:
        """Legacy alias for Pause; preserves the existing EC2 instance."""
        return lifecycle(node_id, "pause", confirm_snooze)

    @mcp.tool()
    def taks_node_wake(node_id: str, confirm_wake: bool = False) -> dict:
        """Legacy alias for Resume; starts the same EC2 instance."""
        return lifecycle(node_id, "resume", confirm_wake)

    @mcp.tool()
    def taks_node_shutdown(node_id: str, confirm_shutdown: bool = False) -> dict:
        """Permanently terminate a node EC2 instance; new Launch required to replace it."""
        if not NODE_ID.fullmatch(node_id):
            return {"ok": False, "error": "Invalid node ID"}
        if not confirm_shutdown:
            return {"ok": False, "confirmation_required": True, "node_id": node_id}
        inventory = api_call("GET", "/api/v2/nodes")
        if not isinstance(inventory, dict) or inventory.get("ok") is False:
            return {"ok": False, "error": "Inventory unavailable"}
        matches = [n for n in inventory.get("items", [])
                   if isinstance(n, dict) and n.get("node_id") == node_id]
        if len(matches) != 1:
            return {"ok": False, "error": "Node not uniquely registered"}
        if matches[0].get("aws_state") not in ("running", "stopped", "pending", "stopping"):
            return {"ok": False, "error": "Invalid lifecycle state",
                    "aws_state": matches[0].get("aws_state")}
        return api_call("POST", "/api/v2/nodes/" + node_id + "/shutdown", {})
