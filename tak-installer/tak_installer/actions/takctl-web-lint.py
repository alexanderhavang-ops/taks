from __future__ import annotations

import subprocess
from pathlib import Path

from tak_installer.engine import Context
from tak_installer.log import get_logger

log = get_logger(__name__)

SRC_ROOT = Path("/opt/taks/takctl")
SRC_WEB_DIR = SRC_ROOT / "web"
LINT_SCRIPT = SRC_WEB_DIR / "lint-ui.sh"


class _Action:
    ID = "takctl-web-lint"

    def inspect(self, ctx: Context) -> int:
        log.info("Inspecting %s action...", self.ID)
        log.info("  src web dir: %s", SRC_WEB_DIR)
        log.info("  lint script: %s", LINT_SCRIPT)
        if not LINT_SCRIPT.is_file():
            log.info("%s: lint script missing; will skip", self.ID)
        return 0

    def apply(self, ctx: Context) -> int:
        log.info("Applying %s action...", self.ID)

        if not LINT_SCRIPT.is_file():
            log.info("%s: lint script missing at %s; skipping", self.ID, LINT_SCRIPT)
            return 0

        p = subprocess.run(
            ["bash", str(LINT_SCRIPT)],
            cwd=str(SRC_WEB_DIR),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        if (p.stdout or "").strip():
            log.info("%s", p.stdout.strip())

        if p.returncode != 0:
            log.error("%s: lint failed rc=%s", self.ID, p.returncode)
            return int(p.returncode)

        log.info("%s: ready", self.ID)
        return 0


ACTION = _Action()
