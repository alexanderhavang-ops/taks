from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from tak_installer.util import log

# --------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------

# Source-of-truth tree (repo)
SRC_ROOT = Path("/opt/taks/takctl/takctl")

# Runtime tree (deployed)
DST_ROOT = Path("/opt/tak/tools/takctl/takctl")

# Minimal, boring exclusions only
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
        # keep logs compact; rsync can be chatty if -v is used (we don't)
        log.info(p.stdout.strip())


def apply(ctx) -> None:
    """
    Install takctl runtime by mirroring the full source tree.

    Source is authoritative.
    Runtime is disposable.
    """
    log.info("takctl-runtime: syncing runtime from source")
    log.info(f"  source:  {SRC_ROOT}")
    log.info(f"  runtime: {DST_ROOT}")

    if not SRC_ROOT.exists():
        raise RuntimeError(f"takctl source tree missing: {SRC_ROOT}")

    # Ensure runtime base exists
    DST_ROOT.mkdir(parents=True, exist_ok=True)

    # Prefer rsync for true mirroring (delete removed files, preserve metadata)
    rsync = shutil.which("rsync")
    if rsync:
        cmd = [
            rsync,
            "-a",
            "--delete",
            *RSYNC_EXCLUDES,
            f"{SRC_ROOT}/",  # trailing slash = copy contents
            f"{DST_ROOT}/",
        ]
        _run(cmd)
        log.info("takctl-runtime: sync complete (rsync)")
        return

    # Fallback: if rsync isn't available, fail loudly (mirroring correctly matters)
    raise RuntimeError("rsync not found; install rsync or add a correct mirror implementation")


# Define the missing _Action class
class _Action:
    ID = "takctl-runtime"

    def inspect(self, ctx) -> int:
        print(f"Inspecting {self.ID} action...")
        # You can implement more inspection logic if needed
        return 0

    def apply(self, ctx) -> int:
        print(f"Applying {self.ID} action...")
        apply(ctx)  # Call the main apply function here
        return 0


# Assign the action to the ACTION variable
ACTION = _Action()

