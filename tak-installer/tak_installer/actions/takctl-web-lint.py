from __future__ import annotations

import subprocess
from pathlib import Path

from tak_installer.engine import Context
from tak_installer.log import get_logger

log = get_logger(__name__)

SRC_ROOT = None  # resolved from ctx.repo_root
SRC_WEB_DIR = None
LINT_SCRIPT = None


class _Action:
    ID = "takctl-web-lint"

    def inspect(self, ctx: Context) -> int:
        src_root = Path(ctx.repo_root) / "takctl"
        src_web_dir = src_root / "web"
        lint_script = src_web_dir / "lint-ui.sh"
        log.info("Inspecting %s action...", self.ID)
        log.info("  src web dir: %s", src_web_dir)
        log.info("  lint script: %s", lint_script)
        if not lint_script.is_file():
            log.info("%s: lint script missing; will skip", self.ID)
        return 0

    def apply(self, ctx: Context) -> int:
        log.info("Applying %s action...", self.ID)

        src_root = Path(ctx.repo_root) / "takctl"
        src_web_dir = src_root / "web"
        lint_script = src_web_dir / "lint-ui.sh"

        if not lint_script.is_file():
            log.info("%s: lint script missing at %s; skipping", self.ID, lint_script)
            return 0

        p = subprocess.run(
            ["bash", str(lint_script)],
            cwd=str(src_web_dir),
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
