from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from tak_installer.util import log

# Web directory paths
SRC_WEB_DIR = Path("/opt/taks/takctl/web")
DST_WEB_DIR = Path("/opt/tak/tools/takctl/web")

# Exclusions for the rsync
RSYNC_EXCLUDES = [
    "--exclude=__pycache__/",
    "--exclude=*.pyc",
    "--exclude=*.pyo",
    "--exclude=*.swp",
    "--exclude=*.swo",
    "--exclude=*~",
]


def _run(cmd: list[str]) -> None:
    p = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if p.returncode != 0:
        raise RuntimeError(f"command failed rc={p.returncode}:\n{' '.join(cmd)}\n\n{p.stdout}")
    if p.stdout.strip():
        log.info(p.stdout.strip())


def apply(ctx) -> None:
    """
    Mirror the static web directory into runtime.

    IMPORTANT:
      - Do NOT preserve source owner/group/perms (source is a dev tree, often ubuntu-owned, sometimes 0600).
      - Enforce deterministic "install-like" permissions on runtime:
          dirs 0755, files 0644
      - Ensure runtime is owned by tak:tak
    """
    log.info("takctl-web-assets: syncing entire web directory to runtime")
    log.info(f"  source:  {SRC_WEB_DIR}")
    log.info(f"  runtime: {DST_WEB_DIR}")

    if not SRC_WEB_DIR.exists():
        raise RuntimeError(f"takctl web directory missing: {SRC_WEB_DIR}")

    DST_WEB_DIR.mkdir(parents=True, exist_ok=True)

    rsync = shutil.which("rsync")
    if not rsync:
        raise RuntimeError("rsync not found; install rsync or add a correct mirror implementation")

    cmd = [
        rsync,
        "-r",                 # recurse (NOT -a; we do not want to preserve metadata)
        "--delete",           # mirror semantics (remove stale runtime files)
        "--no-owner",
        "--no-group",
        "--no-perms",
        "--chmod=Du=rwx,Dgo=rx,Fu=rw,Fgo=r",  # dirs 0755, files 0644 (install-like)
        *RSYNC_EXCLUDES,
        f"{SRC_WEB_DIR}/",
        f"{DST_WEB_DIR}/",
    ]
    _run(cmd)

    # Ownership: runtime should be tak-owned
    subprocess.run(["chown", "-R", "tak:tak", str(DST_WEB_DIR)], check=False)

    log.info("takctl-web-assets: sync complete (rsync install-policy)")


class _Action:
    ID = "takctl-web-assets"

    def inspect(self, ctx) -> int:
        log.info(f"Inspecting {self.ID} action...")
        return 0

    def apply(self, ctx) -> int:
        log.info(f"Applying {self.ID} action...")
        apply(ctx)
        return 0


ACTION = _Action()
