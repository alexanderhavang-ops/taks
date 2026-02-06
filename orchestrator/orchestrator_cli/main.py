#!/usr/bin/env python3
import argparse
import json

def cmd_status(args):
    from orchestrator_core.core import get_status
    status = get_status()
    if args.json:
        print(json.dumps(status, indent=2))
    else:
        print(
            f"provider={status.get('provider')} "
            f"region={status.get('region')} "
            f"nodes={status.get('count')}"
        )

def main():
    p = argparse.ArgumentParser(prog="taks-orch")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_status = sub.add_parser("status", help="Show orchestrator status")
    p_status.add_argument("--json", action="store_true", help="Raw JSON output")
    p_status.set_defaults(func=cmd_status)

    args = p.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
