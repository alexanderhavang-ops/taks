"""Node TAKS MCP catalog: product-level runtime status only."""
import json
from pathlib import Path

TOOLS = [{"name": "runtime_status", "description": "Read TAKCTL runtime availability",
          "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}}]

def call(name, args):
    if name != "runtime_status" or args:
        raise ValueError("Invalid TAKS tool or arguments")
    data = {"takctl_runtime": Path("/opt/tak/tools/takctl").is_dir(),
            "node_config": Path("/etc/taks/unit.json").is_file()}
    return {"content": [{"type": "text", "text": json.dumps(data, sort_keys=True)}]}
