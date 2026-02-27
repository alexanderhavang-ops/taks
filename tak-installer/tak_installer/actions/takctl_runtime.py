from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from tak_installer.util import log

# --------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------

SRC_PKG_ROOT = Path("/opt/taks/takctl/takctl")
SRC_BIN_ROOT = Path("/opt/taks/takctl/bin")

DST_ROOT = Path("/opt/tak/tools/takctl")
DST_WEB_DIR = DST_ROOT / "web"

DST_PKG_ROOT = DST_ROOT / "takctl"
DST_BIN_ROOT = DST_ROOT / "bin"

TAKCTL_STATE_ROOT = Path("/opt/tak/takctl-state")

RSYNC_EXCLUDES = [
    "--exclude=__pycache__/",
    "--exclude=*.pyc",
    "--exclude=*.pyo",
    "--exclude=*.swp",
    "--exclude=*.swo",
    "--exclude=*~",
]


# --------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------

def _run(cmd: list[str]) -> None:
    p = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if p.returncode != 0:
        raise RuntimeError(f"command failed rc={p.returncode}:\n{' '.join(cmd)}\n\n{p.stdout}")
    if p.stdout.strip():
        log.info(p.stdout.strip())


def _rsync_dir(src: Path, dst: Path) -> None:
    rsync = shutil.which("rsync")
    if not rsync:
        raise RuntimeError("rsync not found")

    dst.mkdir(parents=True, exist_ok=True)

    # IMPORTANT:
    # - We do NOT need rsync to preserve owner/group (installer fixes perms after).
    # - Running as non-root would otherwise fail with chown/chgrp attempts.
    cmd = [
        rsync,
        "-a",
        "--delete",
        "--no-owner",
        "--no-group",
        *RSYNC_EXCLUDES,
        f"{src}/",
        f"{dst}/",
    ]
    _run(cmd)


def _ensure_user_group() -> None:
    # group
    if subprocess.run(["getent", "group", "tak"], stdout=subprocess.DEVNULL).returncode != 0:
        _run(["groupadd", "--system", "tak"])

    # user
    if subprocess.run(["id", "-u", "tak"], stdout=subprocess.DEVNULL).returncode != 0:
        _run([
            "useradd",
            "--system",
            "--gid", "tak",
            "--home", "/opt/tak",
            "--shell", "/usr/sbin/nologin",
            "tak",
        ])


def _ensure_runtime_dirs() -> None:
    (DST_ROOT / "secrets").mkdir(parents=True, exist_ok=True)
    (DST_ROOT / "state").mkdir(parents=True, exist_ok=True)


def _fix_runtime_perms() -> None:
    """
    Make runtime predictable WITHOUT breaking the venv.

    Key rule:
      - NEVER chmod the venv tree (especially bin/python symlinks → would chmod /usr/bin/python3.*)
    """
    # Ownership for the whole runtime tree
    subprocess.run(["chown", "-R", "tak:tak", str(DST_ROOT)], check=False)

    # Directories: 2750 (setgid), but prune .venv
    subprocess.run(
        ["bash", "-lc", f'find "{DST_ROOT}" -path "{DST_ROOT}/.venv" -prune -o -type d -exec chmod 2750 {{}} \\;'],
        check=False,
    )

    # Files: 0640, but prune .venv
    subprocess.run(
        ["bash", "-lc", f'find "{DST_ROOT}" -path "{DST_ROOT}/.venv" -prune -o -type f -exec chmod 0640 {{}} \\;'],
        check=False,
    )

    # Runtime helper scripts should be executable (regular files only)
    if DST_BIN_ROOT.exists():
        subprocess.run(
            ["bash", "-lc", f'find "{DST_BIN_ROOT}" -maxdepth 1 -type f -exec chmod 0750 {{}} \\; 2>/dev/null || true'],
            check=False,
        )


    # Web UI assets must be world-readable (static files served by takctl-web).
    # Keep this OUTSIDE the generic 0640/2750 clamp above.
    if DST_WEB_DIR.exists():
        subprocess.run(["bash", "-lc", f'find "{DST_WEB_DIR}" -type d -exec chmod 0755 {{}} \\; 2>/dev/null || true'], check=False)
        subprocess.run(["bash", "-lc", f'find "{DST_WEB_DIR}" -type f -exec chmod 0644 {{}} \\; 2>/dev/null || true'], check=False)


def _ensure_venv() -> None:
    venv_dir = DST_ROOT / ".venv"
    venv_py = venv_dir / "bin" / "python"

    if not venv_py.exists():
        log.info("takctl-runtime: creating runtime venv")
        subprocess.run(["python3", "-m", "venv", str(venv_dir)], check=True)

    # Ownership only; do NOT chmod the venv tree
    subprocess.run(["chown", "-R", "tak:tak", str(venv_dir)], check=False)

    # Upgrade tooling + install deps as tak
    subprocess.run(
        ["sudo", "-u", "tak", str(venv_py), "-m", "pip", "install", "-q", "--upgrade", "pip", "setuptools", "wheel"],
        check=True,
    )

    # takctl-web deps + postgres driver
    subprocess.run(
        ["sudo", "-u", "tak", str(venv_py), "-m", "pip", "install", "-q",
         "fastapi", "uvicorn", "python-multipart", "psycopg2-binary", "requests"],
        check=True,
    )


def _fix_state_perms() -> None:
    # Ensure state root exists and is writable by tak
    TAKCTL_STATE_ROOT.mkdir(parents=True, exist_ok=True)
    subprocess.run(["chown", "-R", "tak:tak", str(TAKCTL_STATE_ROOT)], check=False)
    subprocess.run(["bash", "-lc", f'find "{TAKCTL_STATE_ROOT}" -type d -exec chmod 2770 {{}} \\;'], check=False)
    subprocess.run(["bash", "-lc", f'find "{TAKCTL_STATE_ROOT}" -type f -exec chmod 0660 {{}} \\;'], check=False)


# --------------------------------------------------------------------
# Apply
# --------------------------------------------------------------------

def apply(ctx) -> None:
    log.info("takctl-runtime: ensuring user/group")
    _ensure_user_group()

    if not SRC_PKG_ROOT.exists():
        raise RuntimeError(f"source tree missing: {SRC_PKG_ROOT}")

    log.info("takctl-runtime: syncing runtime")
    _rsync_dir(SRC_PKG_ROOT, DST_PKG_ROOT)

    if SRC_BIN_ROOT.exists():
        _rsync_dir(SRC_BIN_ROOT, DST_BIN_ROOT)

    _ensure_runtime_dirs()
    _fix_runtime_perms()
    _ensure_venv()
    _fix_state_perms()

    log.info("takctl-runtime: ready")


# --------------------------------------------------------------------
# Action wrapper
# --------------------------------------------------------------------

class _Action:
    ID = "takctl-runtime"

    def inspect(self, ctx) -> int:
        print(f"Inspecting {self.ID} action...")
        return 0

    def apply(self, ctx) -> int:
        print(f"Applying {self.ID} action...")
        apply(ctx)
        return 0


ACTION = _Action()
