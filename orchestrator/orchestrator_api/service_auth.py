"""Scoped loopback service authentication for orchestrator MCP operations."""
import hmac
import logging
import os
import re
from pathlib import Path

TOKEN_FILE = Path(os.environ.get("TAKS_ORCH_SERVICE_TOKEN_FILE",
                              "/etc/devops-mcp/service-auth/orchestrator.token"))
STATIC_ALLOWED = {
    ("GET", "/api/v2/units"),
    ("GET", "/api/v2/nodes"),
    ("POST", "/api/v2/nodes/preview"),
    ("POST", "/api/v2/nodes/dry-run"),
    ("POST", "/api/v2/nodes/launch"),
    ("POST", "/api/v2/bundles/readiness"),
    ("POST", "/api/v2/bundles/build"),
}
NODE_TAKS_PROBE = re.compile(r"^/api/v2/nodes/[A-Za-z0-9][A-Za-z0-9_.-]{0,127}/mcp/taks$")
NODE_DEVOPS_PROBE = re.compile(r"^/api/v2/nodes/[A-Za-z0-9][A-Za-z0-9_.-]{0,127}/mcp/devops$")
MARTI_DIAGNOSTICS = re.compile(r"^/api/v2/nodes/[A-Za-z0-9][A-Za-z0-9_.-]{0,127}/marti/diagnostics$")
LIFECYCLE = re.compile(r"^/api/v2/nodes/[A-Za-z0-9][A-Za-z0-9_.-]{0,127}/(?:pause|resume|shutdown|snooze|wake|terminate)$")


def service_auth_ok(request):
    method = request.method.upper()
    path = request.url.path.rstrip("/")
    if (method, path) not in STATIC_ALLOWED and not (method == "POST" and (LIFECYCLE.fullmatch(path) or NODE_DEVOPS_PROBE.fullmatch(path) or NODE_TAKS_PROBE.fullmatch(path) or MARTI_DIAGNOSTICS.fullmatch(path))):
        return False
    # Only the orchestrator host's loopback client may use the service token.
    if not request.client or request.client.host not in ("127.0.0.1", "::1"):
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
        logging.getLogger("taks.service_auth").info("service_token_allowed method=%s path=%s", method, path)
    return valid
