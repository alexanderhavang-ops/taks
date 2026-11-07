"""TAKS business MCP tools. No DevOps diagnostics or filesystem access."""
import json
import re
import urllib.error
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8090"
TOKEN_FILE = Path("/etc/devops-mcp/service-auth/orchestrator.token")
NODE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
UNIT = re.compile(r"^[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*$")


def call(method, path, data=None):
    try:
        token = TOKEN_FILE.read_text(encoding="ascii").strip()
        if not token:
            return {"ok": False, "error": "Service token unavailable"}
        headers = {"Authorization": "Bearer " + token, "Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(BASE + path, method=method, headers=headers,
                                         data=json.dumps(data).encode() if data is not None else None)
        with urllib.request.urlopen(request, timeout=110 if path.endswith("/launch") else 25) as response:
            return json.loads(response.read(2_000_000))
    except (OSError, ValueError, urllib.error.URLError, TimeoutError) as exc:
        return {"ok": False, "error": type(exc).__name__}


def register_taks_tools(mcp, api_call=call):
    @mcp.tool()
    def taks_units_list() -> dict:
        """List TAKS organizational units."""
        return api_call("GET", "/api/v2/units")

    @mcp.tool()
    def taks_nodes_list() -> dict:
        """List TAK nodes and their product-level health."""
        return api_call("GET", "/api/v2/nodes")

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
        return {"ok": True, "node_id": node_id, "aws_state": node.get("aws_state"),
                "status": node.get("status"), "checks": node.get("checks", {})}

    @mcp.tool()
    def taks_node_launch(unit_path: str, confirm_launch: bool = False,
                         fqdn: str = "", instance_type: str = "") -> dict:
        """Provision a paid TAK node only after explicit confirmation."""
        if not confirm_launch:
            return {"ok": False, "confirmation_required": True}
        preview = taks_node_preview(unit_path, fqdn, instance_type)
        if not isinstance(preview, dict) or preview.get("ok") is False:
            return preview
        inventory = api_call("GET", "/api/v2/nodes")
        if not isinstance(inventory, dict) or inventory.get("ok") is False:
            return {"ok": False, "error": "Inventory unavailable"}
        for group in ("items", "untracked_items", "orphaned_items"):
            for node in inventory.get(group, []):
                if isinstance(node, dict) and (node.get("unit_path") == unit_path or
                   (fqdn and node.get("fqdn") == fqdn)) and node.get("aws_state") not in ("terminated", "shutting-down"):
                    return {"ok": False, "error": "Node already exists"}
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
        if state != ("running" if action == "snooze" else "stopped"):
            return {"ok": False, "error": "Invalid lifecycle state", "aws_state": state}
        return api_call("POST", "/api/v2/nodes/" + node_id + "/" + action, {})

    @mcp.tool()
    def taks_node_snooze(node_id: str, confirm_snooze: bool = False) -> dict:
        """Stop a running TAK node after confirmation."""
        return lifecycle(node_id, "snooze", confirm_snooze)

    @mcp.tool()
    def taks_node_wake(node_id: str, confirm_wake: bool = False) -> dict:
        """Start a stopped TAK node after confirmation."""
        return lifecycle(node_id, "wake", confirm_wake)
