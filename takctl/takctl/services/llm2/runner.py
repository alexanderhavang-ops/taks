from __future__ import annotations

import argparse
import time
from typing import Any

from takctl.services.llm2.paths import latest_run_pointer, runs_root, latest_root
from takctl.services.llm2.phase1 import run_phase1
from takctl.services.llm2.phase2 import run_phase2
from takctl.services.llm2.phase3 import run_phase3
from takctl.services.llm2.store import write_json


def _run_id() -> str:
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


def run_once(*, phase: str) -> dict[str, Any]:
    run_id = _run_id()
    # ensure base dirs exist
    (runs_root() / run_id).mkdir(parents=True, exist_ok=True)
    latest_root().mkdir(parents=True, exist_ok=True)

    if phase == "phase1":
        out = run_phase1(run_id=run_id)
    elif phase == "phase2":
        out = run_phase2(run_id=run_id)
    elif phase == "phase3":
        out = run_phase3(run_id=run_id)
    else:
        out = {"ok": False, "run_id": run_id, "error": f"unknown_phase: {phase}"}

    # always write run pointer (even partial failure)
    write_json(latest_run_pointer(), {"ok": True, "run_id": run_id, "phase": phase})
    # write run summary
    write_json(runs_root() / run_id / "run.json", out)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", required=True, choices=["phase1", "phase2", "phase3"])
    ap.add_argument("--once", action="store_true", help="run once and exit")
    args = ap.parse_args()
    out = run_once(phase=args.phase)
    # print minimal (systemd-friendly)
    print(out.get("ok", False))
    print(out.get("run_id", ""))
    print(out.get("phase", ""))


if __name__ == "__main__":
    main()
