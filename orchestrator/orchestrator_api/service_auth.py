"""Narrowly scoped loopback service-token authentication for MCP."""
import hmac
import logging
import os
from pathlib import Path

TOKEN_FILE = Path(os.environ.get(
    "TAKS_ORCH_SERVICE_TOKEN_FILE",
    "/etc/devops-mcp/service-auth/orchestrator.token",
))
ALLOWED = {
    ("GET", "/api/v2/units"),
    ("GET", "/api/v2/nodes"),
    ("POST", "/api/v2/nodes/preview"),
    ("POST", "/api/v2/nodes/dry-run"),
    ("POST", "/api/v2/nodes/launch"),
}

def service_auth_ok(request):
    if (request.method.upper(), request.url.path.rstrip("/")) not in ALLOWED:
        return False
    header = request.headers.get("authorization", "")
    if not header.startswith("Bearer "):
        return False
    supplied = header[7:].strip()
    if not supplied or len(supplied) > 256:
        return False
    try:
        expected = TOKEN_FILE.read_text(encoding="ascii").strip()
    except (OSError, UnicodeError):
        return False
    valid = bool(expected and hmac.compare_digest(supplied, expected))
    if valid:
        logging.getLogger("taks.service_auth").info("service_token_allowed method=%s path=%s", request.method, request.url.path)
    return valid
