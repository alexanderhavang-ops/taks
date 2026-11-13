"""TAKS DevOps MCP gateway with bounded orchestrator deployment."""
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from mcp.server.fastmcp import FastMCP
from app.fs_component import register_fs_tools
from app.shell_component import register_shell_tool
from app.orchestrator_component import register_orchestrator_tools
from app.ops_component import register_ops_tools
from app.deploy_component import register_deploy_tool
from app.route53_component import register_route53_tools
from app.cert_ops_component import register_cert_ops_tools
from app.lifecycle_component import register_lifecycle_tools
from app.node_diagnostics_component import register_node_diagnostics_tools

mcp = FastMCP("TAKS DevOps", host=os.environ.get("MCP_BIND_HOST", "127.0.0.1"), port=int(os.environ.get("MCP_PORT", "8765")),
              stateless_http=True, json_response=True)
PROC = Path(os.environ.get("TAKS_PROC_DIR", "/proc"))
ORCH = Path(os.environ.get("TAKS_ORCH_PATH", "/opt/tak-orch"))
LOG_ROOT = Path(os.environ.get("TAKS_LOG_DIR", "/var/log/tak-orch"))
STATUS = Path(os.environ.get("TAKS_STATUS_FILE", "/var/lib/taks-devops-mcp/orchestrator.json"))
LOG_NAME = os.environ.get("ORCHESTRATOR_LOG_FILE", "orchestrator.log")
MAX_TAIL = 2_000_000

def _text(path, size=8192):
    try:
        return path.read_bytes()[:size].decode("utf-8", "replace")
    except OSError:
        return ""

@mcp.tool()
def gateway_status() -> dict:
    """Gateway version and read-only permissions."""
    return {"name": "taks-devops-mcp", "version": "0.2.1",
            "phase": "deployer", "deployment_enabled": True,
            "capabilities": ["gateway_status", "system_status",
                             "orchestrator_status", "orchestrator_logs", "deploy_orchestrator",
                             "route53_node_dns_status", "route53_node_dns_repair",
                             "state_backup", "backup_verification", "restore_selection",
                             "bundle_preparation", "node_shutdown", "async_operation_status",
                             "node_readonly_diagnostics"]}

@mcp.tool()
def system_status() -> dict:
    """Read host uptime, load, memory and orchestrator filesystem space."""
    uptime = _text(PROC / "uptime")
    load = _text(PROC / "loadavg")
    mem = {k: int(v) * 1024 for k, v in re.findall(
        r"^([A-Za-z_()]+):\s+(\d+)\s+kB", _text(PROC / "meminfo"), re.M)}
    try:
        disk = os.statvfs(ORCH)
        fs = {"total_bytes": disk.f_blocks * disk.f_frsize,
              "available_bytes": disk.f_bavail * disk.f_frsize}
    except OSError:
        fs = {"error": "orchestrator mount unavailable"}
    return {"sample_time": datetime.now(timezone.utc).isoformat(),
            "host_uptime_seconds": float(uptime.split()[0]) if uptime else None,
            "host_load_1_5_15": load.split()[:3] if load else None,
            "host_memory_bytes": {k: mem.get(k) for k in
                                  ("MemTotal", "MemAvailable", "SwapTotal", "SwapFree")},
            "orchestrator_filesystem": fs}

@mcp.tool()
def orchestrator_status() -> dict:
    """Read optional externally generated status snapshot (not a live health probe)."""
    try:
        if not STATUS.is_file():
            return {"available": False, "reason": "No status snapshot installed"}
        if STATUS.stat().st_size > 65536:
            return {"available": False, "reason": "Snapshot too large"}
        snapshot = json.loads(_text(STATUS, 65536))
        if not isinstance(snapshot, dict):
            return {"available": False, "reason": "Snapshot is not an object"}
        return {"available": True, "snapshot": snapshot,
                "snapshot_mtime": STATUS.stat().st_mtime}
    except (OSError, ValueError) as exc:
        return {"available": False, "reason": type(exc).__name__}

@mcp.tool()
def orchestrator_logs(lines: int = 100, contains: str = "") -> dict:
    """Bounded tail of one configured log file; no arbitrary path access."""
    if not 1 <= lines <= 500 or len(contains) > 128:
        return {"error": "lines must be 1..500 and filter <=128 characters"}
    if Path(LOG_NAME).name != LOG_NAME or LOG_NAME in (".", ".."):
        return {"available": False, "reason": "Invalid configured log filename"}
    path = LOG_ROOT / LOG_NAME
    if path.is_symlink() or not path.is_file():
        return {"available": False, "reason": "Log unavailable"}
    try:
        with path.open("rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - MAX_TAIL))
            rows = f.read(MAX_TAIL).decode("utf-8", "replace").splitlines()
        if size > MAX_TAIL and rows:
            rows = rows[1:]
        if contains:
            rows = [r for r in rows if contains.casefold() in r.casefold()]
        out = []
        for row in rows[-lines:]:
            row = re.sub(r"(?i)(authorization:\s*bearer\s+)\S+", r"\1[REDACTED]", row)
            row = re.sub(r"(?i)(password|api[_-]?key|token|secret)([=:]\s*)\S+",
                         r"\1\2[REDACTED]", row)
            out.append(row[:4096])
        return {"available": True, "filename": LOG_NAME, "lines": out,
                "truncated_to_last_bytes": min(size, MAX_TAIL)}
    except OSError as exc:
        return {"available": False, "reason": type(exc).__name__}

register_fs_tools(mcp)
register_shell_tool(mcp)
register_orchestrator_tools(mcp)
register_ops_tools(mcp)
register_deploy_tool(mcp)
register_route53_tools(mcp)
register_cert_ops_tools(mcp)
register_lifecycle_tools(mcp)
register_node_diagnostics_tools(mcp)

if __name__ == "__main__":
    mcp.run(transport="streamable-http")
