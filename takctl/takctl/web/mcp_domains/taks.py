"""TAKS product MCP domain, separate from host DevOps.

Expose the running TAKCTL OpenAPI schema for discovery only. This module
never performs authenticated API calls or turns arbitrary paths into tools.
"""
import json
import urllib.request
from pathlib import Path


_EMPTY = {"type": "object", "properties": {}, "additionalProperties": False}
_SURFACE = {
    "type": "object",
    "properties": {
        "path_prefix": {"type": "string", "description": "Optional HTTP path prefix filter"},
        "include_details": {"type": "boolean", "description": "Return operation schemas and authorization metadata"},
    },
    "additionalProperties": False,
}
TOOLS = [
    {"name": "runtime_status", "description": "Read TAKCTL runtime availability", "inputSchema": _EMPTY},
    {"name": "api_surface", "description": "Discover registered TAKCTL endpoints from the live OpenAPI schema; optionally include operation schemas and security requirements", "inputSchema": _SURFACE},
]
_METHODS = frozenset(("get", "post", "put", "patch", "delete"))


def _surface(schema, prefix="", include_details=False):
    if not isinstance(prefix, str) or len(prefix) > 256 or (prefix and not prefix.startswith("/")):
        raise ValueError("path_prefix must be a valid HTTP path prefix")
    if not isinstance(include_details, bool):
        raise ValueError("include_details must be boolean")
    paths = {}
    for path, operations in schema.get("paths", {}).items():
        if not path.startswith(prefix):
            continue
        methods = {method.upper(): definition for method, definition in operations.items()
                   if method.lower() in _METHODS}
        if not methods:
            continue
        if include_details:
            paths[path] = methods
        else:
            paths[path] = sorted(methods)
    result = {"title": schema.get("info", {}).get("title", "TAKCTL"),
              "version": schema.get("info", {}).get("version"),
              "paths": paths}
    if include_details:
        # Preserve references and security definitions required to interpret
        # nested request/response schema and security declarations.
        result["components"] = schema.get("components", {})
        result["security"] = schema.get("security", [])
    return result


def call(name, args):
    args = args or {}
    if name == "runtime_status":
        if args:
            raise ValueError("Unexpected TAKS tool arguments")
        data = {"takctl_runtime": Path("/opt/tak/tools/takctl").is_dir(),
                "node_config": Path("/etc/taks/unit.json").is_file()}
    elif name == "api_surface":
        if set(args) - {"path_prefix", "include_details"}:
            raise ValueError("Unexpected TAKS tool arguments")
        # Import lazily to avoid startup cycles; discover runtime endpoints,
        # not hard-coded or stale docs. Only loopback is contacted.
        with urllib.request.urlopen("http://127.0.0.1:8080/openapi.json", timeout=5) as response:
            schema = json.load(response)
        data = _surface(schema, args.get("path_prefix", ""), args.get("include_details", False))
    else:
        raise ValueError("Unknown TAKS tool")
    return {"content": [{"type": "text", "text": json.dumps(data, sort_keys=True)}]}


# Extend the product domain while retaining its existing authorization boundary.
import sys as _sim_sys
from takctl.web.mcp_domains.simulation_tools import install as _install_simulation
_install_simulation(_sim_sys.modules[__name__])
