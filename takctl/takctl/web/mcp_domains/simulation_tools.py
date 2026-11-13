"""Narrow Business MCP surface for simulation and Martine reference retrieval."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import socket
import subprocess

SOCKET = "/opt/tak/simulation/control.sock"
DOC_ROOT = Path("/opt/tak/tools/takctl/state/docs")
CONTROL_OPS = ("create", "move", "stop", "deactivate", "activate", "chat", "batch", "entity_move", "entity_stop", "entity_patch", "unit_patch", "marker_put", "marker_remove", "cot_send", "cot_remove", "pause", "resume", "schedule_put", "schedule_cancel", "knowledge_put", "background_put", "background_pause", "background_resume", "background_remove", "xmpp_chat", "mumble_channel", "mumble_ptt")
DOC_TOOLS = {
    "list_reference_docs": ({"only_active": {"type": "boolean"}}, []),
    "search_reference_docs": ({"query": {"type": "string"}, "limit": {"type": "integer"}, "doc_id": {"type": "string"}}, ["query"]),
    "search_reference_docs_semantic": ({"query": {"type": "string"}, "limit": {"type": "integer"}, "doc_id": {"type": "string"}}, ["query"]),
    "get_reference_doc_context": ({"doc_id": {"type": "string"}, "chunk_id": {"type": "string"}, "window": {"type": "integer"}}, ["doc_id", "chunk_id"]),
    "list_reference_doc_sections": ({"doc_id": {"type": "string"}, "limit": {"type": "integer"}}, ["doc_id"]),
    "get_reference_section": ({"doc_id": {"type": "string"}, "section_id": {"type": "string"}, "title_query": {"type": "string"}, "max_chars": {"type": "integer"}}, ["doc_id"]),
}


def tool(name, description, properties, required=()):
    return {"name": name, "description": description, "inputSchema": {
        "type": "object", "properties": properties, "required": list(required), "additionalProperties": False}}


TOOLS = [tool("simulation_read", "Read persistent exercise state, sessions and server-observed positions",
              {"unit_id": {"type": "string"}, "since_revision": {"type": "integer"}, "entity_offset": {"type":"integer"}, "entity_limit": {"type":"integer"}, "entity_id":{"type":"string"},"after_seq":{"type":"integer"},"limit":{"type":"integer"},"view": {"type": "string", "enum": ["status", "capabilities", "export", "orbat", "provisioning", "actor", "events"]}}),
         tool("map_read", "Read OSM geometry/tags, inspect a feature, or look up a mapped pedestrian route; never moves simulation entities",
              {"operation": {"type": "string", "enum": ["config", "area", "feature", "route"]}, "arguments": {"type": "object"}}, ["operation"]),
         tool("simulation_control", "Control units or individuals, patch status, publish markers/custom CoT, send GeoChat, or submit atomic state batches; explicit confirmation required",
              {"operation": {"type": "string", "enum": list(CONTROL_OPS)},
               "arguments": {"type": "object"}, "confirm_write": {"type": "boolean"}}, ["operation", "arguments"])]
TOOLS += [tool(name, "Read Martine reference documents: " + name, props, required)
          for name, (props, required) in DOC_TOOLS.items()]


def simulation(operation, arguments):
    payload = json.dumps({"operation": operation, "arguments": arguments}, allow_nan=False).encode() + b"\n"
    if len(payload) > 65536:
        raise ValueError("Simulation request too large")
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(12)
            client.connect(SOCKET)
            client.sendall(payload)
            with client.makefile("rb") as f:
                data = f.readline(1048577)
        if len(data) > 1048576 or not data.endswith(b"\n"):
            raise ValueError("Simulation response too large or incomplete")
        return json.loads(data)
    except (OSError, TimeoutError):
        return {"ok": False, "error": "Simulation daemon unavailable"}


def reference(name, args):
    if name not in DOC_TOOLS:
        raise ValueError("Reference operation not allowed")
    props, required = DOC_TOOLS[name]
    if not isinstance(args, dict) or set(args) - set(props) or set(required) - set(args):
        raise ValueError("Invalid reference arguments")
    for k, v in args.items():
        typ = props[k]["type"]
        if ((typ == "string" and (not isinstance(v, str) or len(v) > 2000)) or
            (typ == "integer" and type(v) is not int) or
            (typ == "boolean" and type(v) is not bool)):
            raise ValueError("Invalid reference argument type")
    if "limit" in args and not 1 <= args["limit"] <= (500 if name == "list_reference_doc_sections" else 20):
        raise ValueError("Invalid limit")
    if "window" in args and not 0 <= args["window"] <= 3:
        raise ValueError("Invalid window")
    if "max_chars" in args and not 500 <= args["max_chars"] <= 20000:
        raise ValueError("Invalid max_chars")
    if "query" in args and not args["query"].strip():
        raise ValueError("query is required")
    doc_id = args.get("doc_id", "")
    if doc_id and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", doc_id):
        raise ValueError("Invalid doc_id")
    registry = DOC_ROOT / "registry/docs.json"
    if not registry.exists():
        return {"ok": True, "state": "empty", "count": 0, "items": [],
                "message": "No reference documents installed on this node"}
    try:
        items = json.loads(registry.read_text(encoding="utf-8")).get("items", [])
    except (OSError, ValueError):
        return {"ok": False, "error": "Document registry unreadable"}
    active = [r for r in items if isinstance(r, dict) and r.get("active", True)]
    if doc_id and not any(r.get("doc_id") == doc_id for r in active):
        return {"ok": False, "error": "Active reference document not found"}
    if not items or (not active and args.get("only_active", True)):
        return {"ok": True, "state": "empty", "count": 0, "items": [], "message": "No active reference documents"}
    if name != "list_reference_docs" and not any(r.get("status") == "ready" for r in active):
        return {"ok": True, "state": "not_ready", "count": 0, "items": [], "message": "No indexed reference documents"}
    # No model/dependency import for empty installations. Search uses Martine's
    # existing implementation; nothing here generates a model answer.
    python = Path("/opt/tak/tools/martine/.venv/bin/python")
    if not python.is_file():
        return {"ok": False, "error": "Martine reference retrieval runtime unavailable"}
    # Use Martine's own dependency environment. This bounded retrieval worker
    # has no relationship to the daemon's per-identity asynchronous sessions.
    script = ("import json,sys; from martine.tools import docs_ref; "
              "v=json.load(sys.stdin); print(json.dumps(getattr(docs_ref,v['name'])(**v['args']),ensure_ascii=False))")
    env = dict(os.environ, PYTHONPATH="/opt/tak/tools/martine:/opt/tak/tools/takctl")
    try:
        process = subprocess.run([str(python), "-c", script], input=json.dumps({"name": name, "args": args}),
            capture_output=True, text=True, timeout=15, env=env)
        if process.returncode or len(process.stdout) > 500000:
            return {"ok": False, "error": "Martine reference retrieval failed; inspect node logs"}
        return json.loads(process.stdout)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {"ok": False, "error": "Martine reference retrieval unavailable or timed out"}


def call(name, args):
    if name == "map_read":
        from .map_context import read
        if set(args) - {"operation", "arguments"}: raise ValueError("Unknown map tool arguments")
        result = read(args.get("operation"), args.get("arguments", {}))
    elif name in DOC_TOOLS:
        result = reference(name, args)
    elif name == "simulation_read":
        if set(args) - {"unit_id", "since_revision", "view", "entity_offset", "entity_limit", "entity_id", "after_seq", "limit"}:
            raise ValueError("Unknown simulation read arguments")
        args = dict(args); view = args.pop("view", "status")
        if view not in ("status", "capabilities", "export", "orbat", "provisioning", "actor", "events"): raise ValueError("Unknown simulation view")
        if view == "provisioning":
            path=Path("/opt/tak/simulation/provisioning.json")
            if not path.is_file(): result={"ok":True,"stage":"not_started"}
            else:
                raw=path.read_bytes()
                if len(raw)>8192: raise ValueError("Invalid provisioning status size")
                result=json.loads(raw)
        else: result = simulation(view, args if view in ("status", "actor", "events") else {})
    elif name == "simulation_control":
        if set(args) - {"operation", "arguments", "confirm_write"}:
            raise ValueError("Unknown simulation control arguments")
        if args.get("confirm_write") is not True:
            result = {"ok": False, "confirmation_required": True}
        elif args.get("operation") not in CONTROL_OPS:
            raise ValueError("Unknown simulation control operation")
        else:
            result = simulation(args["operation"], args.get("arguments", {}))
    else:
        raise ValueError("Unknown exercise/reference tool")
    return {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, allow_nan=False)}]}


def install(module):
    """Extend a deployed Business domain without replacing its existing tools."""
    if getattr(module, "_simulation_installed", False):
        return
    base = module.call
    names = {t["name"] for t in TOOLS}
    module.TOOLS.extend(t for t in TOOLS if t["name"] not in {x["name"] for x in module.TOOLS})
    for t in module.TOOLS:
        if t["name"] in ("service_read", "service_write"):
            enum = t["inputSchema"]["properties"]["service"].get("enum", [])
            for service in ("simulation", "reference_docs") if t["name"] == "service_read" else ("simulation",):
                if service not in enum:
                    enum.append(service)

    def dispatch(name, args):
        args = args or {}
        if name in names:
            return call(name, args)
        if name in ("service_read", "service_write") and args.get("service") in ("simulation", "reference_docs"):
            if set(args) - {"service", "operation", "arguments", "confirm_write"}:
                raise ValueError("Unknown service arguments")
            if args["service"] == "reference_docs":
                if name != "service_read":
                    raise ValueError("Reference documents are read-only")
                return call(args.get("operation"), args.get("arguments", {})) if args.get("operation") in DOC_TOOLS else call("invalid", {})
            if name == "service_read":
                operation = args.get("operation", "")
                if operation.startswith("map_"):
                    return call("map_read", {"operation": operation[4:], "arguments": args.get("arguments", {})})
                if operation not in ("status", "capabilities", "export", "orbat", "provisioning", "actor", "events"):
                    raise ValueError("Unknown simulation read operation")
                return call("simulation_read", {**args.get("arguments", {}), "view": operation})
            return call("simulation_control", {k: v for k, v in args.items() if k != "service"})
        return base(name, args)

    module.call = dispatch
    module._simulation_installed = True
