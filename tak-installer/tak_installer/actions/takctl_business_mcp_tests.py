"""Run TAKCTL Business MCP permission tests, retaining bounded diagnostic output."""
from __future__ import annotations

import grp
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from tak_installer.util import log

RUNTIME = Path("/opt/tak/tools/takctl")
PYTHON = RUNTIME / ".venv" / "bin" / "python"
REPORT = Path("/var/log/taks-business-mcp-tests.log")


def _redact(value: str) -> str:
    return re.sub(
        r"(?i)(password|secret|api[_-]?key|token)(\s*[:=]\s*)\S+",
        r"\1\2[REDACTED]", value,
    )


def apply(ctx):
    tests = Path(ctx.repo_root) / "takctl" / "tests"
    if not PYTHON.is_file() or not (tests / "test_node_business_mcp.py").is_file():
        raise RuntimeError("TAKCTL Business MCP test runner or source missing")
    proc = subprocess.run(
        [str(PYTHON), "-m", "unittest", "-v", "test_node_business_mcp",
         "test_marti_oauth", "test_ldap_admin_group", "test_live_marti_oauth", "test_admin_user_store_routing",
         "test_business_services", "test_live_business_services"],
        cwd=str(tests),
        env={**os.environ, "PYTHONPATH": str(RUNTIME), "TAKS_MARTI_LIVE_TESTS": "1", "TAKS_SERVICE_LIVE_TESTS": "1"},
        capture_output=True, text=True, timeout=180, check=False,
    )
    output = _redact((proc.stdout or "") + "\n" + (proc.stderr or ""))[-14000:]
    REPORT.write_text(
        f"timestamp={datetime.now(timezone.utc).isoformat()} exit_code={proc.returncode}\n"
        + output, encoding="utf-8",
    )
    os.chown(REPORT, -1, grp.getgrnam("tak").gr_gid)
    REPORT.chmod(0o640)
    statuses = [
        line.strip()[:180] for line in output.splitlines()
        if line.startswith("test_") or line.startswith("Ran ") or line.strip() == "OK"
        or line.startswith(("FAILED (", "ERROR:", "ImportError:", "ModuleNotFoundError:"))
    ]
    log.info("takctl-business-mcp-tests: exit=%s cases=%s", proc.returncode, statuses)
    print("Business MCP regression: exit=%s; %s" % (proc.returncode, " | ".join(statuses[-8:])))
    if proc.returncode:
        raise RuntimeError("Business MCP test failures: node DevOps installer_tail includes the bounded report")


class _Action:
    ID = "takctl-business-mcp-tests"

    def inspect(self, ctx):
        return 0

    def apply(self, ctx):
        apply(ctx)
        return 0


ACTION = _Action()
