"""Scoped loopback service authentication for orchestrator MCP operations."""
import hmac
import hashlib
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
NODE_BACKUP = re.compile(r"^/api/v2/nodes/[A-Za-z0-9][A-Za-z0-9_.-]{0,127}/backup$")
BACKUP_READ = re.compile(r"^/api/v2/units/[A-Za-z0-9_-][A-Za-z0-9_.-]*(?:/[A-Za-z0-9_-][A-Za-z0-9_.-]*)*/backups(?:/restore-selection)?$")
BACKUP_WRITE = re.compile(r"^/api/v2/units/[A-Za-z0-9_-][A-Za-z0-9_.-]*(?:/[A-Za-z0-9_-][A-Za-z0-9_.-]*)*/backups/[A-Za-z0-9][A-Za-z0-9_.-]{0,127}/(?:verify|select-restore)$")


def business_service_token():
    # Domain separated from browser-session signatures; no DevOps-owned file.
    from orchestrator_core.config import load_secrets_config
    secret = load_secrets_config().auth.session_secret
    if not secret:
        raise RuntimeError('Orchestrator session secret unavailable')
    return hmac.new(secret.encode(), b'taks-business-mcp-v1', hashlib.sha256).hexdigest()


def service_auth_ok(request):
    method = request.method.upper()
    path = request.url.path.rstrip("/")
    if (method, path) not in STATIC_ALLOWED and not (
        method == "GET" and BACKUP_READ.fullmatch(path)
        or method == "POST" and (LIFECYCLE.fullmatch(path) or NODE_BACKUP.fullmatch(path)
        or BACKUP_WRITE.fullmatch(path) or NODE_DEVOPS_PROBE.fullmatch(path)
        or NODE_TAKS_PROBE.fullmatch(path) or MARTI_DIAGNOSTICS.fullmatch(path))
    ):
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
        business_match = hmac.compare_digest(supplied, business_service_token())
    except Exception:
        business_match = False
    if business_match:
        return ((method, path) in {('GET','/api/v2/units'),('GET','/api/v2/nodes')}
                or (method == 'POST' and (NODE_TAKS_PROBE.fullmatch(path) or MARTI_DIAGNOSTICS.fullmatch(path))))
    try:
        expected = TOKEN_FILE.read_text(encoding="ascii").strip()
    except (OSError, UnicodeError):
        return False
    valid = bool(expected and hmac.compare_digest(supplied, expected))
    if valid:
        logging.getLogger("taks.service_auth").info("service_token_allowed method=%s path=%s", method, path)
    return valid
