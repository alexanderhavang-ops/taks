from __future__ import annotations

import argparse
import time
from typing import Any

from takctl.services.llm2.paths import latest_root, latest_run_pointer, runs_root
from takctl.services.llm2.phase1 import run_phase1
from takctl.services.llm2.phase2 import run_phase2
from takctl.services.llm2.phase3 import run_phase3
from takctl.services.llm2.store import write_json


def _run_id() -> str:
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


def run_once(*, phase: str, domain: str | None = None) -> dict[str, Any]:
    run_id = _run_id()

    (runs_root() / run_id).mkdir(parents=True, exist_ok=True)
    latest_root().mkdir(parents=True, exist_ok=True)

    dom = (domain or "").strip()
    dom_arg = None if (not dom or dom.lower() == "all") else dom

    if phase == "phase1":
        out = run_phase1(run_id=run_id, domain=dom_arg)
    elif phase == "phase2":
        out = run_phase2(run_id=run_id, domain=dom_arg)
    elif phase == "phase3":
        out = run_phase3(run_id=run_id, domain=dom_arg)
    else:
        out = {"ok": False, "run_id": run_id, "error": f"unknown_phase: {phase}"}

    write_json(
        latest_run_pointer(),
        {
            "ok": True,
            "run_id": run_id,
            "phase": phase,
            "domain": (dom_arg or "all"),
        },
    )
    write_json(runs_root() / run_id / "run.json", out)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", required=True, choices=["phase1", "phase2", "phase3"])
    ap.add_argument("--domain", default="all", help="domain name or 'all'")
    ap.add_argument("--once", action="store_true", help="run once and exit")
    args = ap.parse_args()

    out = run_once(phase=args.phase, domain=args.domain)

    print(out.get("ok", False))
    print(out.get("run_id", ""))
    print(out.get("phase", ""))
    print(out.get("domain", args.domain or "all"))


if __name__ == "__main__":
    main()
