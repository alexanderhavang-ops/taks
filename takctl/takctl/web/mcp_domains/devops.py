"""Constrained, dependency-free host operations on a TAK node.

These run inside TAKCTL under its orchestrator-authenticated mTLS endpoint.
No arbitrary commands, filesystem traversal, secret reads or shell interpretation.
"""
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess

SERVICES = (
    "takserver.service", "takctl-web.service", "nginx.service",
    "postgresql.service", "slapd.service", "mumble-server.service",
    "openfire.service", "martine-cot.service", "taks-heartbeat.timer",
)
PORTS = (80, 443, 8080, 8089, 8443, 8446, 5222, 5432, 389)
SAFE_PATHS = {
    "/opt/tak/CoreConfig.xml", "/etc/nginx/nginx.conf",
    "/var/log/taks-installer-state.log", "/etc/taks-bootstrap.d/config.d/node.conf",
}
MAX_LINES = 80

def schema(properties=None, required=None):
    value = {"type": "object", "properties": properties or {}, "additionalProperties": False}
    if required:
        value["required"] = required
    return value

def entry(name, description, props=None, required=None):
    return {"name": name, "description": description,
            "inputSchema": schema(props, required)}

STR = {"type": "string"}
INT = {"type": "integer", "minimum": 1, "maximum": MAX_LINES}
TOOLS = [
    entry("host_identity", "Hostname and operating system"),
    entry("host_resources", "Memory, load average and root filesystem usage"),
    entry("listening_ports", "Inspect expected TCP ports via kernel socket tables"),
    entry("service_list", "Show status of allowlisted systemd services"),
    entry("service_status", "Inspect one allowlisted systemd service", {"service": STR}, ["service"]),
    entry("service_logs", "Read the last N journal lines of an allowlisted service",
          {"service": STR, "lines": INT}, ["service"]),
    entry("nginx_check", "Validate Nginx configuration without changing it"),
    entry("cert_status", "Inspect node public TLS certificate expiry and SAN without exposing keys"),
    entry("file_stat", "Stat one explicitly allowlisted configuration or installer file",
          {"path": STR}, ["path"]),
    entry("installer_tail", "Read last N bounded installer event lines", {"lines": INT}),
]

def _run(argv, timeout=8, limit=10000):
    try:
        p = subprocess.run(argv, shell=False, stdin=subprocess.DEVNULL,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           timeout=timeout, check=False)
        return {"exit_code": p.returncode,
                "stdout": p.stdout[:limit].decode("utf-8", "replace"),
                "stderr": p.stderr[:1200].decode("utf-8", "replace")}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "error": type(exc).__name__}

def _service(service):
    if not isinstance(service, str) or service not in SERVICES:
        raise ValueError("Unknown or disallowed service")
    return service

def _lines(value):
    if type(value) is not int or not 1 <= value <= MAX_LINES:
        raise ValueError("Invalid line limit")
    return value

def _tail(path, lines):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            from collections import deque
            data = list(deque(f, maxlen=lines))
        return {"lines": "".join(data)[:12000]}
    except OSError as exc:
        return {"ok": False, "error": type(exc).__name__}

def _ports():
    found = set()
    for filename in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            with open(filename, encoding="ascii") as f:
                next(f)
                for line in f:
                    parts = line.split()
                    if len(parts) > 3 and parts[3] == "0A":
                        found.add(int(parts[1].split(":")[1], 16))
        except (OSError, ValueError, StopIteration):
            pass
    return {"ports": [{"port": p, "listening": p in found} for p in PORTS]}

def _resources():
    mem = {}
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, _, value = line.partition(":")
            if key in ("MemTotal", "MemAvailable", "SwapTotal", "SwapFree"):
                mem[key] = value.strip()
        disk = shutil.disk_usage("/")
        return {"memory": mem, "loadavg": list(os.getloadavg()),
                "root_disk": {"total": disk.total, "used": disk.used, "free": disk.free}}
    except OSError as exc:
        return {"ok": False, "error": type(exc).__name__}

def _identity():
    values = {}
    try:
        for line in Path("/etc/os-release").read_text().splitlines():
            if line.startswith(("ID=", "VERSION_ID=", "PRETTY_NAME=")):
                key, value = line.split("=", 1)
                values[key] = value.strip('"')
    except OSError:
        pass
    return {"hostname": socket.gethostname(), "os": values}

def _cert():
    # Public leaf only. Never access or return certificate private keys.
    node = Path("/etc/taks-bootstrap.d/config.d/node.conf")
    fqdn = ""
    try:
        for line in node.read_text().splitlines():
            if line.strip().startswith("fqdn"):
                key, sep, value = line.partition("=")
                if sep and key.strip() == "fqdn":
                    fqdn = value.strip()
                    break
    except OSError:
        pass
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]{0,250}", fqdn or ""):
        return {"ok": False, "error": "Node FQDN unavailable"}
    cert = Path("/etc/letsencrypt/live") / fqdn / "fullchain.pem"
    if not cert.is_file():
        return {"ok": False, "error": "Public certificate missing"}
    return _run(["openssl", "x509", "-in", str(cert), "-noout",
                 "-dates", "-subject", "-ext", "subjectAltName"])

def _invoke(name, args):
    if name == "host_identity":
        return _identity()
    if name == "host_resources":
        return _resources()
    if name == "listening_ports":
        return _ports()
    if name == "service_list":
        return {"services": {s: _run(["systemctl", "is-active", s], limit=200)
                             for s in SERVICES}}
    if name == "service_status":
        return _run(["systemctl", "show", _service(args["service"]),
                     "--property=Id,LoadState,ActiveState,SubState,Result,MainPID,NRestarts"],
                    limit=2500)
    if name == "service_logs":
        return _run(["journalctl", "--no-pager", "--output=short-iso",
                     "-u", _service(args["service"]), "-n", str(_lines(args.get("lines", 40)))],
                    limit=12000)
    if name == "nginx_check":
        return _run(["nginx", "-t"], limit=4000)
    if name == "cert_status":
        return _cert()
    if name == "file_stat":
        path = args["path"]
        if not isinstance(path, str) or path not in SAFE_PATHS:
            raise ValueError("Path not allowlisted")
        try:
            st = Path(path).stat()
            return {"path": path, "bytes": st.st_size, "mode": oct(st.st_mode & 0o777),
                    "modified": int(st.st_mtime)}
        except OSError as exc:
            return {"ok": False, "error": type(exc).__name__}
    if name == "installer_tail":
        return _tail("/var/log/taks-installer-state.log", _lines(args.get("lines", 40)))
    raise ValueError("Unknown DevOps tool")

def call(name, args):
    definitions = {item["name"]: item for item in TOOLS}
    if name not in definitions or not isinstance(args, dict):
        raise ValueError("Unknown tool or arguments")
    keys = definitions[name]["inputSchema"]["properties"]
    required = definitions[name]["inputSchema"].get("required", [])
    if any(k not in keys for k in args) or any(k not in args for k in required):
        raise ValueError("Invalid tool arguments")
    value = _invoke(name, args)
    return {"content": [{"type": "text", "text": json.dumps(value, sort_keys=True)}]}
