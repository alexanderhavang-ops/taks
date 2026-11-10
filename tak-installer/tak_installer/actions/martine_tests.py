"""Run Martine's deterministic SDK/MCP/TAK regressions during node provisioning.

This is a fixed test command. No OpenAI inference calls are made.
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
REPORT = MARTINE / "state" / "logs" / "martine-agent-regressions.txt"

def apply(ctx) -> None:
    if not PYTHON.is_file() or not TESTS.is_dir():
        raise RuntimeError("Martine regression environment missing")
    env = dict(os.environ)
    env["PYTHONPATH"] = f"{MARTINE}:{TAKCTL}"
    env["OPENAI_AGENTS_DISABLE_TRACING"] = "1"
    env.pop("OPENAI_API_KEY", None)
    command = [
        "sudo", "-u", "tak", "env",
        f"PYTHONPATH={env['PYTHONPATH']}",
        "OPENAI_AGENTS_DISABLE_TRACING=1",
        str(PYTHON), "-m", "unittest", "-v",
        "test_agents_migration",
        "test_agents_sdk_workflows",
        "test_chat_scope",
        "test_martine_use_cases",
    ]
    proc = subprocess.run(
        command, text=True, capture_output=True,
        cwd=str(TESTS), timeout=200, check=False,
    )
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(
        f"exit_code={proc.returncode}\n" +
        (proc.stdout + "\n" + proc.stderr)[-30000:],
        encoding="utf-8",
    )
    REPORT.chmod(0o640)
    log.info(
        "martine-tests: exit_code=%s; last lines:\n%s",
        proc.returncode,
        "\n".join((proc.stderr or proc.stdout).splitlines()[-12:]),
    )
    if proc.returncode:
        raise RuntimeError(f"Martine regression failed: exit {proc.returncode}")

class _Action:
    ID = "martine-tests"

    def inspect(self, ctx) -> int:
        print(f"Inspecting {self.ID} action...")
        return 0

    def apply(self, ctx) -> int:
        apply(ctx)
        return 0

ACTION = _Action()
