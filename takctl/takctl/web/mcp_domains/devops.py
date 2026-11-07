"""Node DevOps MCP catalog: OS diagnostics only."""
import os
import json
from pathlib import Path

TOOLS = [{"name": "host_identity", "description": "Read hostname and OS release",
          "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}}]

def call(name, args):
    if name != "host_identity" or args:
        raise ValueError("Invalid DevOps tool or arguments")
    values = {}
    release = Path("/etc/os-release")
    if release.is_file():
        for line in release.read_text(encoding="utf-8").splitlines():
            if line.startswith(("ID=", "VERSION_ID=", "PRETTY_NAME=")):
                key, value = line.split("=", 1)
                values[key] = value.strip('"')
    return {"content": [{"type": "text", "text": json.dumps({"hostname": os.uname().nodename, "os": values}, sort_keys=True)}]}
