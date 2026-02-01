from __future__ import annotations

import argparse
import os
from pathlib import Path

from tak_installer.apply import apply as apply_impl
from tak_installer.engine import Context, discover_actions


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="tak-installer")
    sub = p.add_subparsers(dest="cmd", required=True)

    ap = sub.add_parser("apply", help="Run enabled actions from a plan directory")
    ap.add_argument("--dry-run", action="store_true", help="Inspect only; do not apply")

    rp = sub.add_parser("run", help="Run a single action by ID (ignores plans)")
    rp.add_argument("action_id", help="Action ID, e.g. systemd.takctl-web")
    rp.add_argument("--dry-run", action="store_true", help="Inspect only; do not apply")

    lp = sub.add_parser("list", help="List discovered actions")
    return p


def main() -> int:
    args = build_parser().parse_args()
    repo_root = Path(__file__).resolve().parents[2]

    if args.cmd == "apply":
        print("tak-installer apply")
        print(f"  dry-run: {bool(args.dry_run)}")
        print()
        return apply_impl(repo_root=repo_root, dry_run=bool(args.dry_run))

    if args.cmd == "list":
        actions = discover_actions()
        for aid in sorted(actions.keys()):
            print(aid)
        return 0

    if args.cmd == "run":
        actions = discover_actions()
        aid = args.action_id
        if aid not in actions:
            print(f"ERROR: unknown action: {aid}")
            print("Known actions:")
            for k in sorted(actions.keys()):
                print(f"  {k}")
            return 1

        ctx = Context(repo_root=repo_root, dry_run=bool(args.dry_run), env=dict(os.environ))
        a = actions[aid]
        print(f"tak-installer run {aid}")
        print(f"  dry-run: {ctx.dry_run}")
        print()
        print(f"[{a.ID}]")
        return a.inspect(ctx) if ctx.dry_run else a.apply(ctx)

    return 0
