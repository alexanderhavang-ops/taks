from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from tak_installer.engine import Context
from tak_installer.log import get_logger

log = get_logger(__name__)

SRC = Path("/opt/taks/takctl/scripts")
DST = Path("/opt/tak/tools/takctl/scripts")


def _sync_tree(src: Path, dst: Path) -> None:
    if not src.exists():
        raise RuntimeError(f"missing source scripts dir: {src}")

    # deterministic replace
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)

    # runtime ownership + exec bits
    subprocess.run(["chown", "-R", "tak:tak", str(dst)], check=False)
    subprocess.run(["chmod", "-R", "0755", str(dst)], check=False)


class _Action:
    ID = "takctl.scripts"

    def inspect(self, ctx: Context) -> int:
        log.info("Inspecting %s action...", self.ID)
        log.info("  src: %s", SRC)
        log.info("  dst: %s", DST)
        return 0

    def apply(self, ctx: Context) -> int:
        log.info("Applying %s action...", self.ID)
        _sync_tree(SRC, DST)
        log.info("%s: ready", self.ID)
        return 0


ACTION = _Action()
