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

        # Ensure runtime venv can run FastAPI form endpoints (needs python-multipart).
        # NOTE: deploy script excludes .venv from rsync, so installer must manage venv deps explicitly.
        venv_py = Path("/opt/tak/tools/takctl/.venv/bin/python")
        if venv_py.exists():
            # Fix perms so the service user can install wheels into the venv.
            subprocess.run(["chown", "-R", "tak:tak", "/opt/tak/tools/takctl/.venv"], check=False)

            # Install the one hard requirement we need right now.
            subprocess.run(
                ["sudo", "-u", "tak", str(venv_py), "-m", "pip", "install", "-q", "python-multipart"],
                check=True,
            )
        else:
            log.warning("takctl-runtime: runtime venv missing at %s (python-multipart not enforced)", venv_py)


    # Ensure FastAPI form parsing works (onboarding upload endpoints).
    # Installer-owned: keep runtime venv dependencies correct.
    venv_py = DST_ROOT.parent / ".venv" / "bin" / "python"
    if venv_py.exists():
        subprocess.run(
            ["sudo", "-u", "tak", str(venv_py), "-m", "pip", "install", "-q", "python-multipart"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # --- ENSURE_RUNTIME_TAKCTL_PKG_MARKERS_AND_PERMS ----------------------------
        # Runtime MUST NOT depend on /opt/taks.
        # Ensure:
        #  - takctl is a real package (not namespace): /opt/tak/tools/takctl/takctl/__init__.py
        #  - takctl.services import works:          /opt/tak/tools/takctl/takctl/services/__init__.py
        #  - llm_runs is importable:                /opt/tak/tools/takctl/takctl/services/llm_runs/__init__.py
        #  - user 'tak' can traverse/read the runtime package tree
        #  - runtime venv does NOT point at /opt/taks (no editable .pth)
        def _harden_runtime_imports() -> None:
            import os, glob, site, subprocess
        
            # 1) Kill editable/source pointers so runtime never sees /opt/taks
            try:
                sp = site.getsitepackages()[0]
                for f in glob.glob(os.path.join(sp, "__editable__.takctl-*.pth")):
                    try: os.remove(f)
                    except Exception: pass
                egg_link = os.path.join(sp, "takctl.egg-link")
                try: os.remove(egg_link)
                except Exception: pass
        
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
        
            subprocess.run(["install","-d","-m","2750","-o","ubuntu","-g","tak", pkg], check=False)
            subprocess.run(["install","-d","-m","2750","-o","ubuntu","-g","tak", f"{pkg}/services"], check=False)
            subprocess.run(["install","-d","-m","2750","-o","ubuntu","-g","tak", f"{pkg}/services/llm_runs"], check=False)
        
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
            subprocess.run(["chgrp","-R","tak", pkg], check=False)
            subprocess.run(["bash","-lc", 'find "$1" -type d -exec chmod 2750 {} \;' , "--", pkg], check=False)
            subprocess.run(["bash","-lc", 'find "$1" -type f -exec chmod 0640 {} \;' , "--", pkg], check=False)
        
        try:
            _harden_runtime_imports()
        except Exception:
            pass
        # ---------------------------------------------------------------------------
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



