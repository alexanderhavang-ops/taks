from __future__ import annotations
import shutil
import subprocess
from pathlib import Path
from tak_installer.util import log

# Web directory paths
SRC_WEB_DIR = Path("/opt/taks/takctl/web")
DST_WEB_DIR = Path("/opt/tak/tools/takctl/web")

# Exclusions for the rsync (we exclude certain files as before)
RSYNC_EXCLUDES = [
    "--exclude=__pycache__/",
    "--exclude=*.pyc",
    "--exclude=*.pyo",
    "--exclude=*.swp",
    "--exclude=*.swo",
    "--exclude=*~",
]


def _run(cmd: list[str]) -> None:
    """Helper function to run shell commands."""
    p = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if p.returncode != 0:
        raise RuntimeError(f"command failed rc={p.returncode}:\n{' '.join(cmd)}\n\n{p.stdout}")
    if p.stdout.strip():
        log.info(p.stdout.strip())


def apply(ctx) -> None:
    """Sync the entire web directory (assets + web) to the runtime."""
    log.info("takctl-web-assets: syncing entire web directory to runtime")
    log.info(f"  source:  {SRC_WEB_DIR}")
    log.info(f"  runtime: {DST_WEB_DIR}")

    if not SRC_WEB_DIR.exists():
        raise RuntimeError(f"takctl web directory missing: {SRC_WEB_DIR}")

    # Ensure runtime web directory exists
    DST_WEB_DIR.mkdir(parents=True, exist_ok=True)

    # Prefer rsync for true mirroring (delete removed files, preserve metadata)
    rsync = shutil.which("rsync")
    if rsync:
        cmd = [
            rsync,
            "-a",
            "--delete",
            *RSYNC_EXCLUDES,
            f"{SRC_WEB_DIR}/",  # Trailing slash copies contents of the directory
            f"{DST_WEB_DIR}/",  # Ensure correct target path
        ]
        _run(cmd)

        log.info("takctl-web-assets: sync complete (rsync)")
        return

    raise RuntimeError("rsync not found; install rsync or add a correct mirror implementation")


# Define the action class
class _Action:
    ID = "takctl-web-assets"

    def inspect(self, ctx) -> int:
        log.info(f"Inspecting {self.ID} action...")
        return 0

    def apply(self, ctx) -> int:
        log.info(f"Applying {self.ID} action...")
        apply(ctx)  # Call the main apply function here
        return 0


# Assign the action to the ACTION variable
ACTION = _Action()

