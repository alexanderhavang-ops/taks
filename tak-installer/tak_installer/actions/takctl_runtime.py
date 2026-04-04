from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from tak_installer.util import log

# --------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------

SRC_PKG_ROOT = None  # resolved from ctx.repo_root
SRC_BIN_ROOT = None  # resolved from ctx.repo_root
SRC_REPLAY_ROOT = None  # resolved from ctx.repo_root

DST_ROOT = Path("/opt/tak/tools/takctl")
DST_WEB_DIR = DST_ROOT / "web"

DST_PKG_ROOT = DST_ROOT / "takctl"
DST_BIN_ROOT = DST_ROOT / "bin"
DST_REPLAY_ROOT = DST_ROOT / "replay"

TAKCTL_STATE_ROOT = Path("/opt/tak/takctl-state")
REPLAY_RUNTIME_ROOT = Path("/opt/tak/replay")

RSYNC_EXCLUDES = [
    "--exclude=__pycache__/",
    "--exclude=*.pyc",
    "--exclude=*.pyo",
    "--exclude=*.swp",
    "--exclude=*.swo",
    "--exclude=*~",
]


def _parse_simple_kv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out

def _truthy(v: str) -> bool:
    return str(v or "").strip().lower() in {"1", "true", "yes", "on"}

def _replay_enabled(ctx) -> bool:
    runtime_conf = Path("/opt/tak/tools/takctl/conf.d/replay.conf")
    merged = _parse_simple_kv(runtime_conf)
    return _truthy(merged.get("replay_enabled", "false"))


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

    IMPORTANT:
      - Do NOT recurse over the whole DST_ROOT; state/ uploads grow over time.
      - Only normalize installer-owned code/config trees.
      - NEVER chmod the venv tree.
    """
    managed_dirs = [
        DST_PKG_ROOT,
        DST_BIN_ROOT,
        DST_WEB_DIR,
        DST_ROOT / "conf.d",
        DST_ROOT / "secrets.d",
        DST_ROOT / "confmeta",
        DST_ROOT / "secrets",
        DST_ROOT / "scripts",
        DST_ROOT / "assets",
        DST_ROOT / "ignite",
        DST_ROOT / "llm",
        DST_ROOT / "llm-infra",
        DST_REPLAY_ROOT,
    ]

    managed_files = [
        DST_ROOT / "takctl.conf",
        DST_ROOT / "secrets.conf",
    ]

    writable_cfg_dirs = {
        str(DST_ROOT / "conf.d"),
        str(DST_ROOT / "secrets.d"),
    }

    for d in managed_dirs:
        if not d.exists():
            continue
        subprocess.run(["chown", "-R", "tak:tak", str(d)], check=False)
        dir_mode = "2770" if str(d) in writable_cfg_dirs else "2750"
        subprocess.run(
            ["bash", "-lc", f'find "{d}" -type d -exec chmod {dir_mode} {{}} \\; 2>/dev/null || true'],
            check=False,
        )
        subprocess.run(
            ["bash", "-lc", f'find "{d}" -type f -exec chmod 0640 {{}} \\; 2>/dev/null || true'],
            check=False,
        )

    for f in managed_files:
        if not f.exists():
            continue
        subprocess.run(["chown", "tak:tak", str(f)], check=False)
        subprocess.run(["chmod", "0640", str(f)], check=False)

    if DST_BIN_ROOT.exists():
        subprocess.run(
            ["bash", "-lc", f'find "{DST_BIN_ROOT}" -maxdepth 1 -type f -exec chmod 0750 {{}} \\; 2>/dev/null || true'],
            check=False,
        )

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
         "fastapi", "uvicorn", "python-multipart", "psycopg2-binary", "requests", "mcp", "pypdf", "fastembed"],
        check=True,
    )


def _fix_state_perms() -> None:
    # Ensure state root exists and is writable by tak
    TAKCTL_STATE_ROOT.mkdir(parents=True, exist_ok=True)
    subprocess.run(["chown", "-R", "tak:tak", str(TAKCTL_STATE_ROOT)], check=False)
    subprocess.run(["bash", "-lc", f'find "{TAKCTL_STATE_ROOT}" -type d -exec chmod 2770 {{}} \\;'], check=False)
    subprocess.run(["bash", "-lc", f'find "{TAKCTL_STATE_ROOT}" -type f -exec chmod 0660 {{}} \\;'], check=False)


def _ensure_replay_runtime_dirs() -> None:
    (REPLAY_RUNTIME_ROOT / "state" / "agents").mkdir(parents=True, exist_ok=True)
    (REPLAY_RUNTIME_ROOT / "logs").mkdir(parents=True, exist_ok=True)


def _fix_replay_runtime_perms() -> None:
    managed_dirs = [
        REPLAY_RUNTIME_ROOT,
        REPLAY_RUNTIME_ROOT / "state",
        REPLAY_RUNTIME_ROOT / "state" / "agents",
        REPLAY_RUNTIME_ROOT / "logs",
    ]

    for d in managed_dirs:
        if not d.exists():
            continue
        subprocess.run(["chown", "tak:tak", str(d)], check=False)
        subprocess.run(["chmod", "2770", str(d)], check=False)


# --------------------------------------------------------------------
# Apply
# --------------------------------------------------------------------

def apply(ctx) -> None:
    log.info("takctl-runtime: ensuring user/group")
    _ensure_user_group()

    src_pkg_root = Path(ctx.repo_root) / "takctl" / "takctl"
    src_bin_root = Path(ctx.repo_root) / "takctl" / "bin"
    src_replay_root = Path(ctx.repo_root) / "takctl" / "replay"

    if not src_pkg_root.exists():
        raise RuntimeError(f"source tree missing: {src_pkg_root}")

    log.info("takctl-runtime: syncing runtime")
    _rsync_dir(src_pkg_root, DST_PKG_ROOT)

    if src_bin_root.exists():
        _rsync_dir(src_bin_root, DST_BIN_ROOT)

    if _replay_enabled(ctx):
        log.info("takctl-runtime: replay enabled -> syncing replay runtime")
        if src_replay_root.exists():
            _rsync_dir(src_replay_root, DST_REPLAY_ROOT)
    else:
        log.info("takctl-runtime: replay disabled -> removing replay runtime code if present")
        if DST_REPLAY_ROOT.exists():
            shutil.rmtree(DST_REPLAY_ROOT)

    _ensure_runtime_dirs()
    _fix_runtime_perms()
    _ensure_venv()
    _fix_state_perms()

    if _replay_enabled(ctx):
        _ensure_replay_runtime_dirs()
        _fix_replay_runtime_perms()

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
