from __future__ import annotations

import os
from pathlib import Path

from tak_installer.engine import Context, load_plan_dir, run_plan


INSTALL_ENV = Path("/etc/tak/install.env")


def _load_install_env() -> dict[str, str]:
    """
    Parse /etc/tak/install.env (KEY=VALUE format).

    This mirrors the shell installer behavior so that headless
    installs and re-applies behave deterministically.
    """
    env: dict[str, str] = {}

    if not INSTALL_ENV.exists():
        return env

    try:
        for line in INSTALL_ENV.read_text(encoding="utf-8").splitlines():
            line = line.strip()

            if not line or line.startswith("#"):
                continue

            if "=" not in line:
                continue

            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    except Exception:
        pass

    return env


def apply(repo_root: Path, dry_run: bool) -> int:
    print("tak-installer apply")
    print(f"  dry-run: {dry_run}")
    print()

    default_plan_dir = repo_root / "tak-installer" / "plans" / "tak-node.d"
    plan_dir = Path(os.environ.get("TAKS_PLAN_DIR", str(default_plan_dir)))

    print(f"plan_dir: {plan_dir}")

    env = dict(os.environ)
    env.update(_load_install_env())

    ctx = Context(
        repo_root=repo_root,
        dry_run=dry_run,
        env=env,
    )

    plan_ids = load_plan_dir(plan_dir)

    return run_plan(ctx, plan_ids)
