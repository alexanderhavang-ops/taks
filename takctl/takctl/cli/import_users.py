from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from takctl.onboarding.import_users_preview import preview_import
from takctl.onboarding.import_users import run_import
from takctl.api.onboarding_identity import build_service

def main() -> int:
    ap = argparse.ArgumentParser(prog="takctl-import-users")
    ap.add_argument("file", help="Path to .xlsx or .csv")
    ap.add_argument("--preview", action="store_true", help="Show header mapping + sample rows as interpreted users")
    ap.add_argument("--dry-run", action="store_true", help="Run import in dry-run mode (no writes)")
    ap.add_argument("--apply", action="store_true", help="Perform import")
    ap.add_argument("--update-existing", action="store_true", help="Update existing users")
    ap.add_argument("--sample-n", type=int, default=8, help="Rows to preview")
    args = ap.parse_args()

    mode_n = int(bool(args.preview)) + int(bool(args.dry_run)) + int(bool(args.apply))
    if mode_n != 1:
        raise SystemExit("Pick exactly one of --preview / --dry-run / --apply")

    if args.preview:
        out = preview_import(args.file, sample_n=args.sample_n)
        print(json.dumps(out, indent=2, sort_keys=True))
        return 0

    svc = build_service()
    res = run_import(
        svc,
        str(Path(args.file).expanduser()),
        dry_run=bool(args.dry_run),
        update_existing=bool(args.update_existing),
    )
    print(json.dumps(res, indent=2, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
