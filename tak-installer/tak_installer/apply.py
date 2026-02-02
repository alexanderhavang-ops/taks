from __future__ import annotations

import os
from pathlib import Path

from tak_installer.engine import Context, load_plan_dir, run_plan


def apply(repo_root: Path, dry_run: bool) -> int:
    default_plan_dir = repo_root / "tak-installer" / "plans" / "tak-node.d"
    plan_dir = Path(os.environ.get("TAKS_PLAN_DIR", str(default_plan_dir)))

    print(f"plan_dir: {plan_dir}")

    plan_ids = load_plan_dir(plan_dir)
    if not plan_ids:
        print("NOTE: plan is empty (no actions enabled).")
        return 0

    ctx = Context(repo_root=repo_root, dry_run=dry_run, env=dict(os.environ))
    return run_plan(ctx, plan_ids)
