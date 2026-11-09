"""Authenticated TAKCTL business MCP domain.

The orchestrator's per-node bearer secret authenticates the outer MCP route.
Only these reviewed operations can be called; OpenAPI discovery is *not* an
arbitrary HTTP proxy. Requests stay on TAKCTL loopback. Passwords and soldier
card tokens never leave this module through MCP.
"""
import json
import re
import urllib.error
import urllib.request
from pathlib import Path

_LOOPBACK = "http://127.0.0.1:8080"

_EMPTY = {"type": "object", "properties": {}, "additionalProperties": False}
_SURFACE = {"type": "object", "properties": {
    "path_prefix": {"type": "string"},
    "include_details": {"type": "boolean"},
}, "additionalProperties": False}
_STR = {"type": "string"}
_USER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,180}\.[^@\s]{2,30}$")
_FQDN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.-]{2,250}$")
TOOLS = [
    {"name": "runtime_status", "description": "Read TAKCTL runtime availability", "inputSchema": _EMPTY},
    {"name": "api_surface", "description": "Discover live TAKCTL OpenAPI routes (discovery, not permission to execute them)", "inputSchema": _SURFACE},
    {"name": "takctl_health", "description": "Read TAKCTL health over fixed loopback endpoint", "inputSchema": _EMPTY},
    {"name": "onboarding_user_create",
     "description": "Create a non-admin TAK test user, with generated password and onboarding context; explicit confirmation required",
     "inputSchema": {"type": "object", "properties": {
         "username": _STR, "email": _STR, "callsign": _STR,
         "group": _STR, "confirm_create": {"type": "boolean"},
     }, "required": ["username", "email"], "additionalProperties": False}},
    {"name": "onboarding_send_invite",
     "description": "Send a TAKCTL soldier-card onboarding email to an existing user; explicit confirmation required",
     "inputSchema": {"type": "object", "properties": {
         "username": _STR, "email": _STR, "confirm_send": {"type": "boolean"},
     }, "required": ["username", "email"], "additionalProperties": False}},
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
        if methods:
            paths[path] = methods if include_details else sorted(methods)
    out = {"title": schema.get("info", {}).get("title", "TAKCTL"),
           "version": schema.get("info", {}).get("version"), "paths": paths}
    if include_details:
        out["components"] = schema.get("components", {})
        out["security"] = schema.get("security", [])
    return out


def _node_fqdn():
    # Bootstrap's unit.json has no fqdn. Runtime conf.d is authoritative.
    from takctl.config import load_config
    fqdn = str(load_config().get("fqdn", "") or "").strip().lower()
    if not _FQDN.fullmatch(fqdn) or ".." in fqdn or "." not in fqdn:
        raise ValueError("Node public FQDN unavailable")
    return fqdn


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _request(method, path, data=None, public_fqdn=None):
    """Fixed loopback transport. No arbitrary URLs/paths supplied by MCP."""
    if not path.startswith("/api/") or "//" in path or ".." in path or "?" in path:
        raise ValueError("Invalid internal TAKCTL path")
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if public_fqdn:
        headers.update({"Host": public_fqdn, "X-Forwarded-Host": public_fqdn,
                        "X-Forwarded-Proto": "https"})
    raw = None if data is None else json.dumps(data, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(
        _LOOPBACK + path, data=raw, method=method, headers=headers)
    opener = urllib.request.build_opener(_NoRedirect())
    try:
        with opener.open(request, timeout=35) as response:
            if response.headers.get_content_type() != "application/json":
                raise ValueError("Unexpected TAKCTL response type")
            blob = response.read(131073)
            if len(blob) > 131072:
                raise ValueError("TAKCTL response too large")
            return json.loads(blob)
    except urllib.error.HTTPError as exc:
        # Do not echo backend errors: they can contain identity data.
        if exc.code == 404:
            return {"ok": False, "not_found": True}
        return {"ok": False, "error": "TAKCTL rejected request", "http_status": exc.code}
    except (OSError, TimeoutError, ValueError) as exc:
        return {"ok": False, "error": "TAKCTL request failed", "reason": type(exc).__name__}


def _identity(username, email):
    if not isinstance(username, str) or not _USER.fullmatch(username):
        raise ValueError("Invalid TAK username")
    if not isinstance(email, str) or len(email) > 254 or not _EMAIL.fullmatch(email):
        raise ValueError("Invalid email")
    return username, email


def call(name, args):
    if not isinstance(args, dict):
        raise ValueError("Tool arguments must be an object")
    declared = next((t for t in TOOLS if t["name"] == name), None)
    if declared is None or set(args) - set(declared["inputSchema"]["properties"]):
        raise ValueError("Unknown tool or arguments")
    if name == "runtime_status":
        return {"content": [{"type": "text", "text": json.dumps({
            "takctl_runtime": Path("/opt/tak/tools/takctl").is_dir(),
            "node_config": Path("/etc/taks/unit.json").is_file()})}]}
    if name == "api_surface":
        with urllib.request.urlopen(_LOOPBACK + "/openapi.json", timeout=5) as response:
            result = _surface(json.load(response), args.get("path_prefix", ""),
                              args.get("include_details", False))
    elif name == "takctl_health":
        result = _request("GET", "/api/health")
    elif name == "onboarding_user_create":
        username, email = _identity(args.get("username"), args.get("email"))
        if args.get("confirm_create") is not True:
            result = {"ok": False, "confirmation_required": True}
        else:
            callsign = str(args.get("callsign") or username).strip()
            group = str(args.get("group") or "").strip()
            if len(callsign) > 64 or len(group) > 64 or (
                group and not _USER.fullmatch(group)
            ):
                raise ValueError("Invalid callsign or group")
            fqdn = _node_fqdn()
            path = "/api/onboarding/users/" + username
            # Preserve an existing user's password, identity and group policy.
            existing = _request("GET", path, public_fqdn=fqdn)
            if existing.get("not_found") is not True:
                result = ({"ok": False, "error": "User already exists", "username": username}
                          if existing.get("ok") is not False else existing)
            else:
                created = _request("POST", path + "/create", {
                    "admin": False,
                    "ctx": {"email": email},
                    "configured_callsign": callsign,
                    "groups_rw": [group] if group else [],
                    "reveal_password": True,
                }, public_fqdn=fqdn)
                result = {"ok": bool(isinstance(created, dict) and
                                     (created.get("user") or {}).get("username") == username),
                          "username": username, "email": email}
                if not result["ok"]:
                    result["error"] = created.get("error", "Create failed") if isinstance(created, dict) else "Create failed"
    elif name == "onboarding_send_invite":
        username, email = _identity(args.get("username"), args.get("email"))
        if args.get("confirm_send") is not True:
            result = {"ok": False, "confirmation_required": True}
        else:
            fqdn = _node_fqdn()
            sent = _request("POST", "/api/onboarding/users/" + username + "/email-link",
                            {"email": email, "reveal_password": True}, public_fqdn=fqdn)
            status = sent.get("email_status") if isinstance(sent, dict) else None
            result = {"ok": bool(isinstance(status, dict) and status.get("ok")),
                      "username": username, "email": email,
                      "delivery": status.get("delivery") if isinstance(status, dict) else None}
            if not result["ok"]:
                result["error"] = sent.get("error", "Invite failed") if isinstance(sent, dict) else "Invite failed"
    else:
        raise ValueError("Unknown TAKS business tool")
    # Keep the MCP return type compatible with the existing node bridge.
    return {"content": [{"type": "text", "text": json.dumps(result, sort_keys=True)}]}
