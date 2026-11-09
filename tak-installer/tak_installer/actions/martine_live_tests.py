"""Run paid live Martine/OpenAI integration tests during provisioning.

Fixed two-case command, bounded timeout, no arbitrary shell or credentials in events.
A failure prevents install/main from being reported as successful.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from tak_installer.util import log

MARTINE = Path("/opt/tak/tools/martine")
TAKCTL = Path("/opt/tak/tools/takctl")
TESTS = MARTINE / "tests"
PYTHON = MARTINE / ".venv" / "bin" / "python"
REPORT = MARTINE / "state" / "logs" / "martine-live-inference.txt"


def apply(ctx) -> None:
    if not PYTHON.is_file() or not (TESTS / "test_live_inference.py").is_file():
        raise RuntimeError("Martine live test environment missing")
    command = [
        "sudo", "-u", "tak", "env",
        f"PYTHONPATH={MARTINE}:{TAKCTL}",
        "MARTINE_LIVE_TESTS=1",
        "OPENAI_AGENTS_DISABLE_TRACING=1",
        str(PYTHON), "-m", "unittest", "-v", "test_live_inference",
    ]
    proc = subprocess.run(
        command, cwd=str(TESTS), text=True,
        capture_output=True, timeout=240, check=False,
    )
    # No model outputs, secrets or traceback text in the node report.
    statuses = [
        line.strip()[:200] for line in proc.stderr.splitlines()
        if line.strip().startswith("test_real_") or line.strip().startswith("Ran ")
        or line.strip() == "OK" or line.strip().startswith("FAILED (")
    ]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(
        f"exit_code={proc.returncode}\n" + "\n".join(statuses) + "\n",
        encoding="utf-8",
    )
    REPORT.chmod(0o640)
    log.info("martine-live-tests: exit=%s cases=%s", proc.returncode, statuses)
    if proc.returncode:
        raise RuntimeError(f"Martine live inference tests failed (exit={proc.returncode})")


class _Action:
    ID = "martine-live-tests"

    def inspect(self, ctx) -> int:
        return 0

    def apply(self, ctx) -> int:
        apply(ctx)
        return 0


ACTION = _Action()
