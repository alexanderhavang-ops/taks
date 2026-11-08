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
    entry("cert_status", "Inspect node public TLS certificate expiry and SAN without exposing keys",
          {"fqdn": STR}, ["fqdn"]),
    entry("file_stat", "Stat one explicitly allowlisted configuration or installer file",
          {"path": STR}, ["path"]),
    entry("installer_tail", "Read last N bounded installer event lines", {"lines": INT}),
    entry("java_processes", "Sample TAK Java process CPU and RSS without command-line arguments"),
    entry("netstat_listeners", "Read selected TCP listeners and visible owning PIDs"),
    entry("lsof_tak_java", "Summarize open file descriptors for identified TAK JVMs without paths"),
    entry("takserver_logs", "Discover allowlisted TAK Server logs or read a bounded tail",
          {"file": STR, "lines": INT}),
    entry("takserver_readiness", "Combine TAK listeners, Java CPU and auth backend readiness"),
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

def _cert(fqdn):
    # The caller supplies the registered node FQDN. The bootstrap node.conf
    # is intentionally root-readable only, and must never be opened here.
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]{0,250}", fqdn or ""):
        return {"ok": False, "error": "Node FQDN unavailable"}
    cert = Path("/etc/letsencrypt/live") / fqdn / "fullchain.pem"
    if not cert.is_file():
        return {"ok": False, "error": "Public certificate missing"}
    return _run(["openssl", "x509", "-in", str(cert), "-noout",
                 "-dates", "-subject", "-ext", "subjectAltName"])


# Read-only TAK Server startup observability. Never expose Java command lines,
# full CoreConfig.xml, authentication records, or arbitrary filesystem paths.
TAK_LOG_DIRS = ("/opt/tak/logs", "/opt/tak/log", "/var/log/takserver")
TAK_LOG_SUFFIXES = (".log", ".out")
def _java_snapshot():
    found = {}
    proc = Path("/proc")
    for path in proc.iterdir():
        if not path.name.isdigit():
            continue
        try:
            comm = (path / "comm").read_text().strip()
            if comm != "java":
                continue
            raw = (path / "cmdline").read_bytes().lower()
            if b"takserver" not in raw and b"marti" not in raw and b"tak." not in raw:
                continue
            fields = (path / "stat").read_text().rsplit(") ", 1)[1].split()
            ticks = int(fields[11]) + int(fields[12])
            rss_pages = int((path / "statm").read_text().split()[1])
            found[int(path.name)] = (ticks, rss_pages)
        except (OSError, ValueError, IndexError):
            continue
    return found

def _java_processes():
    import time
    before = _java_snapshot()
    time.sleep(0.3)
    after = _java_snapshot()
    hz = os.sysconf("SC_CLK_TCK")
    page = os.sysconf("SC_PAGE_SIZE")
    entries = []
    for pid, (ticks, rss) in after.items():
        previous = before.get(pid)
        cpu = round(100.0 * (ticks - previous[0]) / (0.3 * hz), 1) if previous else None
        entries.append({"pid": pid, "cpu_pct_one_core": cpu,
                        "rss_mb": round(rss * page / 1048576, 1)})
    return {"java_processes": sorted(entries, key=lambda x: -(x["cpu_pct_one_core"] or 0))[:12],
            "sample_seconds": 0.3}

def _tak_log_files():
    files = {}
    for root in TAK_LOG_DIRS:
        directory = Path(root)
        if not directory.is_dir() or directory.is_symlink():
            continue
        try:
            for p in directory.iterdir():
                if (not p.is_symlink() and p.is_file()
                        and p.name.lower().endswith(TAK_LOG_SUFFIXES)):
                    files[p.name] = str(p)
        except OSError:
            continue
    return files

def _takserver_logs(args):
    names = _tak_log_files()
    selected = args.get("file", "")
    if selected:
        if selected not in names:
            raise ValueError("TAK log filename not in discovered allowlist")
        files = [selected]
    else:
        files = sorted(names)[:30]
    if not selected:
        return {"files": [{"name": name, "path": names[name]} for name in files],
                "hint": "Specify a discovered filename to read a bounded tail"}
    result = _tail(names[selected], _lines(args.get("lines", 40)))
    if "lines" in result:
        # Avoid emitting common credential assignment patterns from logs.
        result["lines"] = re.sub(
            r"(?im)(password|passwd|secret|token|credential|api[_-]?key)(\s*[:=]\s*)\S+",
            r"\1\2[REDACTED]", result["lines"])
    return {"file": selected, **result}


def _netstat_listeners():
    """Selected TCP listeners, including visible owning process information."""
    result = _run(["ss", "-H", "-ltnp"], timeout=5, limit=20000)
    if result.get("exit_code") != 0:
        return {"available": False, "detail": result.get("stderr", "")[:250]}
    entries = []
    for line in result.get("stdout", "").splitlines():
        parts = line.split(None, 5)
        if len(parts) < 5:
            continue
        local = parts[3]
        try:
            port = int(local.rsplit(":", 1)[-1])
        except ValueError:
            continue
        if port not in PORTS:
            continue
        owner = parts[5] if len(parts) == 6 else ""
        pids = sorted(set(int(x) for x in re.findall(r"pid=(\d+)", owner)))
        entries.append({"port": port, "address": local, "pids": pids})
    return {"listeners": entries, "visibility": "PIDs only when visible to the node MCP user"}

def _lsof_tak_java():
    """Count TAK JVM file descriptors; never return the raw paths or command lines."""
    pids = sorted(_java_snapshot())[:12]
    if not pids:
        return {"pids": [], "open_files": [], "hint": "No TAK JVM process"}
    result = _run(["lsof", "-nP", "-p", ",".join(map(str, pids)), "-Fpt"],
                  timeout=7, limit=25000)
    if result.get("exit_code") not in (0, 1):
        return {"available": False, "error": result.get("stderr", "")[:150]}
    by_pid = {}
    pid = None
    for line in result.get("stdout", "").splitlines():
        if line.startswith("p") and line[1:].isdigit():
            pid = int(line[1:])
            by_pid.setdefault(pid, {"pid": pid, "total": 0, "sockets": 0, "regular_files": 0})
        elif line.startswith("t") and pid in by_pid:
            entry = by_pid[pid]
            entry["total"] += 1
            if line[1:] in ("IPv4", "IPv6", "sock"):
                entry["sockets"] += 1
            elif line[1:] == "REG":
                entry["regular_files"] += 1
    return {"open_files": list(by_pid.values()), "tool": "lsof", "paths_exposed": False}

def _takserver_readiness():
    ports = _ports()
    watched = {x["port"]: x["listening"] for x in ports["ports"]}
    core = Path("/opt/tak/CoreConfig.xml")
    auth = {"backend": "unknown", "file_expected": None, "file_present": None}
    if core.is_file():
        try:
            import xml.etree.ElementTree as ET
            root = ET.parse(core).getroot()
            nodes = [e for e in root.iter() if e.tag.rsplit("}", 1)[-1].lower() == "auth"]
            if nodes:
                auth_node = nodes[0]
                auth["backend"] = auth_node.attrib.get("default", "file")
                files = [e for e in auth_node.iter() if e.tag.rsplit("}", 1)[-1].lower() == "file"]
                if files:
                    location = files[0].attrib.get("location", "")
                    if location and not Path(location).is_absolute() and ".." not in Path(location).parts:
                        auth["file_expected"] = True
                        auth["file_present"] = (core.parent / location).is_file()
                elif auth["backend"].lower() == "ldap":
                    auth["file_expected"] = False
        except (OSError, ET.ParseError):
            auth["error"] = "CoreConfig not readable or parseable"
    return {"coreconfig_present": core.is_file(), "auth": auth,
            "tak_listeners": {str(p): watched.get(p, False) for p in (8089, 8443, 8446)},
            "java": _java_processes(),
            "tak_log_files": list(sorted(_tak_log_files()))[:30]}

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
        return _run(["sudo", "-n", "/usr/sbin/nginx", "-t"], limit=4000)
    if name == "cert_status":
        return _cert(args["fqdn"])
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
    if name == "netstat_listeners":
        return _netstat_listeners()
    if name == "lsof_tak_java":
        return _lsof_tak_java()
    if name == "java_processes":
        return _java_processes()
    if name == "takserver_logs":
        return _takserver_logs(args)
    if name == "takserver_readiness":
        return _takserver_readiness()
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
