"""Serve the bootstrap diagnostics over nginx's private systemd socket."""

import hmac
import json
import os
from http.server import BaseHTTPRequestHandler
from pathlib import Path
import socket
from socketserver import UnixStreamServer

from . import devops

ENDPOINT = "/api/orchestrator/mcp/devops"
TOOL_NAMES = {
    "host_identity", "host_resources", "installer_tail", "listening_ports",
    "memory_read", "service_logs", "service_status",
}
TOOLS = [tool for tool in devops.TOOLS if tool["name"] in TOOL_NAMES]
MAX_BODY = 65536


class Handler(BaseHTTPRequestHandler):
    def setup(self):
        self.request.settimeout(2)
        super().setup()

    def log_message(self, format, *args):
        # Unix sockets have no peer address to log.
        pass

    def respond(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != ENDPOINT:
            return self.respond(404, {"detail": "Unknown MCP endpoint"})
        scheme, _, token = self.headers.get("Authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not hmac.compare_digest(
            token.strip().encode(), self.server.node_secret
        ):
            return self.respond(401, {"detail": "Invalid orchestrator credential"})
        if self.headers.get_content_type() != "application/json":
            return self.respond(415, {"detail": "JSON required"})
        length = self.headers.get("Content-Length", "")
        if not length.isascii() or not length.isdecimal() or len(length) > 5:
            return self.respond(400, {"detail": "Invalid request length"})
        if int(length) > MAX_BODY:
            return self.respond(413, {"detail": "Request too large"})
        try:
            message = json.loads(self.rfile.read(int(length)))
        except (ValueError, RecursionError):
            return self.respond(400, {"detail": "Invalid JSON"})
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or "id" not in message:
            return self.respond(400, {"detail": "Invalid JSON-RPC request"})
        result = self.dispatch(message)
        if result is not None:
            self.respond(200, {"jsonrpc": "2.0", "id": message["id"], "result": result})

    def dispatch(self, message):
        params = message.get("params", {})
        if not isinstance(params, dict):
            return self.respond(400, {"detail": "Invalid parameters"})
        if message.get("method") == "tools/list":
            return {"tools": TOOLS}
        if message.get("method") != "tools/call":
            return self.respond(400, {"detail": "Unsupported MCP method"})
        name = params.get("name")
        if not isinstance(name, str) or name not in TOOL_NAMES:
            return self.respond(400, {"detail": "Tool unavailable during bootstrap"})
        try:
            return devops.call(name, params.get("arguments", {}))
        except ValueError as exc:
            return self.respond(400, {"detail": str(exc)})


def main():
    credentials = Path(os.environ["CREDENTIALS_DIRECTORY"])
    config = (credentials / "node-secret").read_text()
    for line in config.splitlines():
        key, _, value = line.partition("=")
        if key.strip() == "orchestrator_node_secret" and value.strip():
            node_secret = value.strip().encode()
            break
    else:
        raise RuntimeError("Missing node credential")
    if int(os.environ.get("LISTEN_PID", "0")) != os.getpid() or os.environ.get("LISTEN_FDS") != "1":
        raise RuntimeError("Expected one systemd listener")
    with UnixStreamServer("", Handler, bind_and_activate=False) as server:
        server.socket.close()
        server.socket = socket.socket(fileno=3)
        server.node_secret = node_secret
        server.serve_forever()


if __name__ == "__main__":
    main()
