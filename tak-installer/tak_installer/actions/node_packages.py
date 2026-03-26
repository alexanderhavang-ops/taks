from __future__ import annotations

import subprocess

from tak_installer.log import get_logger

log = get_logger(__name__)

PACKAGES = [
    "python3-venv",
    "python3.10-venv",
    "python3-pip",
    "rsync",
    "nginx",
]

def _run(cmd: list[str]) -> None:
    p = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if p.returncode != 0:
        raise RuntimeError(f"command failed rc={p.returncode}:\n{' '.join(cmd)}\n\n{p.stdout}")
    if (p.stdout or "").strip():
        log.info((p.stdout or "").strip())

class _Action:
    ID = "node-packages"

    def inspect(self, ctx) -> int:
        log.info("Inspecting %s action...", self.ID)
        log.info("  packages: %s", ", ".join(PACKAGES))
        return 0

    def apply(self, ctx) -> int:
        log.info("Applying %s action...", self.ID)
        _run(["apt-get", "update"])
        _run(["apt-get", "install", "-y", *PACKAGES])
        log.info("%s: ready", self.ID)
        return 0

ACTION = _Action()
