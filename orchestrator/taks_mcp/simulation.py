"""Explicit simulation/reference tools through the existing authenticated bridge."""
import json
import re


def register_simulation_tools(mcp, api_call):
    def call(node_id, name, arguments):
        if not isinstance(node_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", node_id):
            return {"ok": False, "error": "Invalid node ID"}
        result = api_call("POST", "/api/v2/nodes/" + node_id + "/mcp/taks", {
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": name, "arguments": arguments}})
        try:
            return json.loads(next(c["text"] for c in result["result"]["content"] if c.get("type") == "text"))
        except (KeyError, TypeError, ValueError, StopIteration):
            return {"ok": False, "error": "Node tool unavailable", "detail": result.get("error") if isinstance(result, dict) else None}

    @mcp.tool()
    def taks_node_simulation_read(node_id: str, unit_id: str = "", since_revision: int = 0, view: str = "status") -> dict:
        """Read persistent exercise state, connection health and server-observed positions."""
        return call(node_id, "simulation_read", {"unit_id": unit_id, "since_revision": since_revision, "view": view})

    @mcp.tool()
    def taks_node_map_read(node_id: str, operation: str = "config", arguments: dict | None = None) -> dict:
        """Inspect OpenStreetMap features/geometry or a mapped walking route. Operations: config, area(center/radius_m/kinds/limit/offset/query), feature(feature_id), route(start/end/speed_mps). Read-only; routing never moves entities."""
        return call(node_id, "map_read", {"operation": operation, "arguments": arguments or {}})

    @mcp.tool()
    def taks_node_simulation_control(node_id: str, operation: str, arguments: dict,
                                     confirm_write: bool = False) -> dict:
        """MVP2: create profiles, move/stop individuals or units, atomic batch, patch metadata/health, markers/custom CoT, GeoChat, pause/resume, and explicit schedule_put/schedule_cancel. Read capabilities before writing. No formation/planning/inference loop."""
        if confirm_write is not True:
            return {"ok": False, "confirmation_required": True}
        return call(node_id, "simulation_control", {"operation": operation, "arguments": arguments, "confirm_write": True})

    @mcp.tool()
    def taks_node_reference_docs(node_id: str, operation: str = "list_reference_docs", arguments: dict | None = None) -> dict:
        """Read Martine document catalog, keyword/semantic searches, passages and sections."""
        if operation not in {"list_reference_docs", "search_reference_docs", "search_reference_docs_semantic",
                             "get_reference_doc_context", "list_reference_doc_sections", "get_reference_section"}:
            return {"ok": False, "error": "Reference operation not allowed"}
        return call(node_id, operation, arguments or {})
