from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from tak_installer.util import log

# --------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------

# Source-of-truth trees (repo)
SRC_PKG_ROOT = Path("/opt/taks/takctl/takctl")   # python package
SRC_BIN_ROOT = Path("/opt/taks/takctl/bin")     # helper scripts (must be executable)

# Runtime trees (deployed)
DST_PKG_ROOT = Path("/opt/tak/tools/takctl/takctl")
DST_BIN_ROOT = Path("/opt/tak/tools/takctl/bin")

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
        log.info(p.stdout.strip())


def _rsync_dir(src: Path, dst: Path, *, extra: list[str] | None = None) -> None:
    rsync = shutil.which("rsync")
    if not rsync:
        raise RuntimeError("rsync not found; install rsync or add a correct mirror implementation")

    dst.mkdir(parents=True, exist_ok=True)

    cmd = [
        rsync,
        "-a",         # archive: preserves mode, times, symlinks, etc.
        "--delete",
        *(extra or []),
        *RSYNC_EXCLUDES,
        f"{src}/",    # trailing slash = copy contents
        f"{dst}/",
    ]
    _run(cmd)




def _ensure_bin_exec_perms(dst_bin: Path) -> None:
    """
    Ensure helper scripts are executable after apply.

    Why: some historical deploy paths (or copy implementations) can land helpers as 0644,
    which makes sudo exec fail with "command not found".
    """
    if not dst_bin.exists():
        return
    for p in dst_bin.iterdir():
        if not p.is_file():
            continue
        # Add execute bit for user/group/other conservatively.
        # (We want helpers runnable under sudoers rule.)
        try:
            mode = p.stat().st_mode & 0o777
            if mode & 0o111:
                continue
            os.chmod(p, mode | 0o111)
        except Exception:
            pass


def apply(ctx) -> None:
    """
    Install takctl runtime by mirroring the full source trees.

    Source is authoritative.
    Runtime is disposable.
    """
    log.info("takctl-runtime: syncing runtime from source")
    log.info(f"  source pkg: {SRC_PKG_ROOT}")
    log.info(f"  dest   pkg: {DST_PKG_ROOT}")
    log.info(f"  source bin: {SRC_BIN_ROOT}")
    log.info(f"  dest   bin: {DST_BIN_ROOT}")

    if not SRC_PKG_ROOT.exists():
        raise RuntimeError(f"takctl source package tree missing: {SRC_PKG_ROOT}")

    # 1) Mirror python package tree
    _rsync_dir(SRC_PKG_ROOT, DST_PKG_ROOT)
    log.info("takctl-runtime: sync complete (pkg)")

    # 2) Mirror helper bin tree (critical: preserve executable bits)
    if SRC_BIN_ROOT.exists():
        _rsync_dir(SRC_BIN_ROOT, DST_BIN_ROOT, extra=[])
        _ensure_bin_exec_perms(DST_BIN_ROOT)
        log.info("takctl-runtime: sync complete (bin)")
    else:
        log.warning("takctl-runtime: source bin tree missing: %s (skipping)", SRC_BIN_ROOT)

    # 3) Ensure runtime venv can run FastAPI form endpoints (needs python-multipart).
    # NOTE: deploy script excludes .venv from rsync, so installer must manage venv deps explicitly.
    venv_py = Path("/opt/tak/tools/takctl/.venv/bin/python")
    if venv_py.exists():
        # Fix perms so the service user can install wheels into the venv.
        subprocess.run(["chown", "-R", "tak:tak", "/opt/tak/tools/takctl/.venv"], check=False)
        subprocess.run(
            ["sudo", "-u", "tak", str(venv_py), "-m", "pip", "install", "-q", "python-multipart"],
            check=True,
        )
    else:
        log.warning("takctl-runtime: runtime venv missing at %s (python-multipart not enforced)", venv_py)

    # Ensure FastAPI form parsing works (onboarding upload endpoints).
    venv_py2 = DST_PKG_ROOT.parent / ".venv" / "bin" / "python"
    if venv_py2.exists():
        subprocess.run(
            ["sudo", "-u", "tak", str(venv_py2), "-m", "pip", "install", "-q", "python-multipart"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # --- ENSURE_RUNTIME_TAKCTL_PKG_MARKERS_AND_PERMS ----------------------------
        # Runtime MUST NOT depend on /opt/taks.
        def _harden_runtime_imports() -> None:
            import glob
            import site

            # 1) Kill editable/source pointers so runtime never sees /opt/taks
            try:
                sp = site.getsitepackages()[0]
                for f in glob.glob(os.path.join(sp, "__editable__.takctl-*.pth")):
                    try:
                        os.remove(f)
                    except Exception:
                        pass
                egg_link = os.path.join(sp, "takctl.egg-link")
                try:
                    os.remove(egg_link)
                except Exception:
                    pass

                # Ensure runtime root is always on sys.path
                pth = os.path.join(sp, "zzz-runtime-takctl-root.pth")
                try:
                    with open(pth, "w", encoding="utf-8") as f:
                        f.write("/opt/tak/tools/takctl\n")
                except Exception:
                    pass
            except Exception:
                pass

            # 2) Ensure runtime package markers exist
            pkg = "/opt/tak/tools/takctl/takctl"
            if not os.path.isdir(pkg):
                return

            subprocess.run(["install", "-d", "-m", "2750", "-o", "ubuntu", "-g", "tak", pkg], check=False)
            subprocess.run(["install", "-d", "-m", "2750", "-o", "ubuntu", "-g", "tak", f"{pkg}/services"], check=False)
            subprocess.run(
                ["install", "-d", "-m", "2750", "-o", "ubuntu", "-g", "tak", f"{pkg}/services/llm_runs"], check=False
            )

            def touch(path: str, content: str) -> None:
                if os.path.exists(path):
                    return
                try:
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(content)
                except Exception:
                    pass

            touch(f"{pkg}/__init__.py", "# runtime package marker\n")
            touch(f"{pkg}/services/__init__.py", "# runtime services package marker\n")
            touch(f"{pkg}/services/llm_runs/__init__.py", "# runtime llm_runs package marker\n")

            # 3) Perms/ownership so user 'tak' can import
            subprocess.run(["chgrp", "-R", "tak", pkg], check=False)
            subprocess.run(["bash", "-lc", 'find "$1" -type d -exec chmod 2750 {} \\;', "--", pkg], check=False)
            subprocess.run(["bash", "-lc", 'find "$1" -type f -exec chmod 0640 {} \\;', "--", pkg], check=False)

        try:
            _harden_runtime_imports()
        except Exception:
            pass
        # ---------------------------------------------------------------------------
        return


# Define the missing _Action class
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
