"""Fail node provisioning if Business MCP permissions or redaction regress."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from tak_installer.util import log

RUNTIME = Path("/opt/tak/tools/takctl")
PYTHON = RUNTIME / ".venv" / "bin" / "python"


def apply(ctx):
    tests = Path(ctx.repo_root) / "takctl" / "tests"
    if not PYTHON.is_file() or not (tests / "test_node_business_mcp.py").is_file():
        raise RuntimeError("TAKCTL Business MCP regression files missing")
    proc = subprocess.run(
        [str(PYTHON), "-m", "unittest", "-v", "test_node_business_mcp"],
        cwd=str(tests), env={**os.environ, "PYTHONPATH": str(RUNTIME)},
        capture_output=True, text=True, timeout=90, check=False)
    statuses = [
        line.strip()[:180] for line in proc.stderr.splitlines()
        if line.startswith("test_") or line.startswith("Ran ") or line.strip() == "OK"
        or line.startswith("FAILED (")
    ]
    log.info("takctl-business-mcp-tests: exit=%s cases=%s", proc.returncode, statuses)
    if proc.returncode:
        # Detailed traceback stays in installer log, not the public MCP response.
        raise RuntimeError("TAKCTL Business MCP regression suite failed")


class _Action:
    ID = "takctl-business-mcp-tests"

    def inspect(self, ctx):
        return 0

    def apply(self, ctx):
        apply(ctx)
        return 0


ACTION = _Action()
