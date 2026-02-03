from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import subprocess


def _script_path(ctx) -> Path:
    """
    Prefer repo-root relative script path when ctx provides it, fall back to /opt/taks.
    """
    # ctx may expose repo_root depending on installer engine
    repo_root = getattr(ctx, "repo_root", None) if ctx is not None else None
    if repo_root:
        p = Path(repo_root) / "tak-installer/scripts/deploy-takctl-runtime"
        return p
    return Path("/opt/taks/tak-installer/scripts/deploy-takctl-runtime")


@dataclass
class TakctlRuntimeDeploy:
    ID: str = "takctl-runtime"

    def inspect(self, ctx) -> int:
        script = _script_path(ctx)
        if not script.exists():
            print(f"ERROR: deploy script missing: {script}")
            return 2

        env = dict(os.environ)
        env["DRY_RUN"] = "1"

        try:
            subprocess.run([str(script)], env=env, check=True)
            return 0
        except subprocess.CalledProcessError as e:
            # Return the script's exit code without a python traceback.
            return int(e.returncode or 1)

    def apply(self, ctx) -> int:
        script = _script_path(ctx)
        if not script.exists():
            print(f"ERROR: deploy script missing: {script}")
            return 2

        env = dict(os.environ)
        env["DRY_RUN"] = "0"

        try:
            subprocess.run([str(script)], env=env, check=True)
            return 0
        except subprocess.CalledProcessError as e:
            return int(e.returncode or 1)


ACTION = TakctlRuntimeDeploy()
