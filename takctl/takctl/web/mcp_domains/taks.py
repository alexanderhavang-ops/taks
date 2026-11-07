"""TAKS product MCP domain. Deliberately distinct from host DevOps.

API discovery exposes the TAKCTL FastAPI OpenAPI catalog so clients can
see the actual TAKS API surface without guessing endpoint names. Operations
remain behind explicit tool authorization; discovery is not a generic
privilege-escalating HTTP proxy.
"""
import json
import urllib.request
from pathlib import Path

TOOLS = [
    {"name": "runtime_status", "description": "Read TAKCTL runtime availability",
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "api_surface", "description": "List TAKCTL HTTP API paths and methods from the running application's OpenAPI schema",
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
]


def call(name, args):
    if args:
        raise ValueError("Unexpected TAKS tool arguments")
    if name == "runtime_status":
        data = {"takctl_runtime": Path("/opt/tak/tools/takctl").is_dir(),
                "node_config": Path("/etc/taks/unit.json").is_file()}
    elif name == "api_surface":
        # Import lazily to avoid startup cycles; use the app's registered
        # routes rather than hard-coded or stale API documentation.
        with urllib.request.urlopen("http://127.0.0.1:8080/openapi.json", timeout=5) as response:
            schema = json.load(response)
        data = {
            "title": schema.get("info", {}).get("title", "TAKCTL"),
            "paths": {
                path: sorted(method.upper() for method in operations
                             if method.lower() in {"get", "post", "put", "patch", "delete"})
                for path, operations in schema.get("paths", {}).items()
            },
        }
    else:
        raise ValueError("Unknown TAKS tool")
    return {"content": [{"type": "text", "text": json.dumps(data, sort_keys=True)}]}
