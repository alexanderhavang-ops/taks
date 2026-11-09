"""Read-only Marti diagnostics using the installer-managed TAK admin identity."""
import base64
import json
import re
import ssl
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

from orchestrator_core.nodes_state import get_node
from orchestrator_core.unit_bootstrap import effective_bootstrap_for_bundle

NODE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
FQDN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.-]{0,251}[A-Za-z0-9]$")
PATHS = {
    "subscriptions": "/Marti/api/subscriptions/all",
    "version": "/Marti/api/server/version",
    "enrollment": "/Marti/api/tls/config",
}
LIMIT = 1_048_576


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _redact(value):
    if isinstance(value, dict):
        return {k: ("[REDACTED]" if any(word in k.lower() for word in
                ("password", "secret", "token", "privatekey", "authorization")) else _redact(v))
                for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(v) for v in value]
    return value


def _flatten(files):
    values = {}
    for name in sorted(files):
        values.update(files[name])
    return values


def diagnose(node_id):
    if not isinstance(node_id, str) or not NODE.fullmatch(node_id):
        return {"ok": False, "error": "Invalid node ID"}
    node = get_node(node_id)
    if not node:
        return {"ok": False, "error": "Unknown node"}
    host = str(node.get("fqdn") or "")
    unit = str(node.get("unit_path") or "")
    if not FQDN.fullmatch(host) or ".." in host or "." not in host or not unit:
        return {"ok": False, "error": "Node registry incomplete"}
    try:
        bootstrap = effective_bootstrap_for_bundle(unit)
        cfg = _flatten(bootstrap.get("conf_d", {}))
        secrets = _flatten(bootstrap.get("secrets_d", {}))
        username = str(cfg.get("takctl_admin_user") or "admin").strip()
        password = str(secrets.get("takctl_admin_password") or "").strip()
        if not username or not password:
            return {"ok": False, "error": "Installer TAK admin credential unavailable"}
        auth = base64.b64encode((username + ":" + password).encode()).decode("ascii")
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}), NoRedirect(),
            urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    except (OSError, ValueError):
        return {"ok": False, "error": "TAK admin configuration unavailable"}
    checks = {}
    for name, path in PATHS.items():
        request = urllib.request.Request("https://" + host + ":8446" + path,
            headers={"Authorization": "Basic " + auth, "Accept": "application/json, application/xml"}, method="GET")
        try:
            with opener.open(request, timeout=5) as response:
                body = response.read(LIMIT + 1)
                if len(body) > LIMIT:
                    checks[name] = {"ok": False, "error": "Response too large"}
                    continue
                check = {"ok": True, "http_status": response.status}
                try:
                    check["data"] = _redact(json.loads(body))
                except (ValueError, UnicodeError):
                    try:
                        check["xml_root"] = ET.fromstring(body).tag
                    except ET.ParseError:
                        check["bytes"] = len(body)
                checks[name] = check
        except urllib.error.HTTPError as exc:
            checks[name] = {"ok": False, "http_status": exc.code}
        except (OSError, ValueError):
            checks[name] = {"ok": False, "error": "Marti connection failed"}
    return {"ok": checks.get("subscriptions", {}).get("ok", False), "node_id": node_id,
            "admin_user": username, "credential_source": "installer takctl_admin_password",
            "checks": checks}
