from __future__ import annotations

import os
import subprocess
from pathlib import Path

from tak_installer.util import log

BIN_DIR = Path("/opt/tak/tools/takctl/bin")
SCRIPT = BIN_DIR / "takctl-llm-kick"

# Default one-shot unit to start (override via env or first CLI arg to script)
DEFAULT_SERVICE = os.environ.get("TAKCTL_LLM_KICK_SERVICE", "takctl-llm-refresh-tactical.service")


def _write_script(service_default: str) -> None:
    BIN_DIR.mkdir(parents=True, exist_ok=True)

    body = f"""#!/usr/bin/env bash
set -euo pipefail

svc="${{1:-{service_default}}}"

# Kick once
sudo systemctl start "$svc"

# Show quick status (non-fatal)
sudo systemctl --no-pager --full status "$svc" || true
"""

    tmp = SCRIPT.with_suffix(".tmp")
    tmp.write_text(body, encoding="utf-8")
    tmp.chmod(0o750)
    tmp.replace(SCRIPT)

    # Match existing bin tools: tak:tak 750 (best-effort)
    try:
        subprocess.run(["chown", "tak:tak", str(SCRIPT)], check=True)
    except Exception as e:
        log.info(f"takctl.llm-kick: chown skipped/failed: {e}")


def apply(ctx) -> None:
    _write_script(DEFAULT_SERVICE)


class _Action:
    ID = "takctl.llm-kick"

    def inspect(self, ctx) -> int:
        log.info(f"Inspecting {self.ID} action...")
        log.info(f"  script:   {SCRIPT}")
        log.info(f"  default:  {DEFAULT_SERVICE}")
        log.info("  usage:    /opt/tak/tools/takctl/bin/takctl-llm-kick [systemd-unit]")
        return 0

    def apply(self, ctx) -> int:
        log.info(f"Applying {self.ID} action...")
        apply(ctx)
        log.info(f"{self.ID}: installed -> {SCRIPT}")
        return 0


ACTION = _Action()
