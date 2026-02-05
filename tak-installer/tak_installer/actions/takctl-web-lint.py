from __future__ import annotations

import subprocess
from pathlib import Path

from tak_installer.util import log

SRC_WEB_DIR = Path("/opt/taks/takctl/web")
LINT_SCRIPT = SRC_WEB_DIR / "lint-ui.sh"


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def apply(ctx) -> None:
    """
    Best-effort UI lint. This must NEVER hard-fail an offline/airgapped installer.
    If tools are missing, lint-ui.sh will SKIP and exit 0.
    If lint finds issues, lint-ui.sh exits 0 (unless --strict is used).
    """
    if not SRC_WEB_DIR.is_dir():
        log.info(f"takctl-web-lint: skip (missing {SRC_WEB_DIR})")
        return

    if not LINT_SCRIPT.exists():
        log.info(f"takctl-web-lint: skip (missing {LINT_SCRIPT})")
        return

    log.info("takctl-web-lint: running best-effort UI lint")
    p = _run([str(LINT_SCRIPT)], cwd=SRC_WEB_DIR)

    out = (p.stdout or "").strip()
    if out:
        log.info(out)

    # Never fail the installer.
    if p.returncode != 0:
        log.info(f"takctl-web-lint: non-zero rc={p.returncode} (ignored; best-effort)")


class _Action:
    ID = "takctl-web-lint"

    def inspect(self, ctx) -> int:
        log.info(f"Inspecting {self.ID} action...")
        return 0

    def apply(self, ctx) -> int:
        log.info(f"Applying {self.ID} action...")
        apply(ctx)
        return 0


ACTION = _Action()

