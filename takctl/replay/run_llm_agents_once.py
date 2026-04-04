from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))
if str(SCRIPT_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT.parent))
from typing import Any, Dict, List

from replay_paths import STATE_ROOT, ensure_runtime_dirs
from takctl.config import load_config


def role_rank(role: str) -> int:
    return {
        "battalion": 0,
        "company": 1,
        "platoon": 2,
        "staff_tross_platoon": 2,
        "group": 3,
    }.get(str(role or ""), 9)


def iter_agents() -> List[Path]:
    out: List[Path] = []
    if not STATE_ROOT.exists():
        return out
    for p in sorted(STATE_ROOT.iterdir()):
        if p.is_dir() and (p / "state.json").exists():
            out.append(p)
    return out


def main() -> None:
    cfg = load_config()

    ap = argparse.ArgumentParser()
    ap.add_argument("--sim-time", type=int, required=True)
    ap.add_argument("--temperature", type=float, default=float(cfg.llm_temperature))
    ap.add_argument("--max-tokens", type=int, default=int(cfg.llm_n_predict))
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--callsigns", default="", help="optional comma-separated subset")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    ensure_runtime_dirs()

    selected = None
    if args.callsigns.strip():
        selected = {x.strip().upper() for x in args.callsigns.split(",") if x.strip()}

    candidates: List[tuple[int, str, Dict[str, Any]]] = []

    for d in iter_agents():
        callsign = d.name.upper()
        state_path = d / "state.json"
        if not state_path.exists():
            continue
        st = json.loads(state_path.read_text(encoding="utf-8"))
        agent = dict(st.get("agent") or {})
        callsign = str(agent.get("callsign") or d.name).upper()

        if selected is not None and callsign not in selected:
            continue

        if str(agent.get("control_mode") or "") != "llm":
            continue

        role = str(agent.get("role") or "")
        candidates.append((role_rank(role), callsign, st))

    candidates.sort(key=lambda x: (x[0], x[1]))

    ran = 0
    errors = 0

    for _, callsign, st in candidates:
        agent = dict(st.get("agent") or {})
        role = str(agent.get("role") or "unit")
        superior = str(agent.get("superior") or "")
        mission = str(agent.get("mission") or "")

        cmd = [
            sys.executable,
            str(SCRIPT_ROOT / "unit_agent.py"),
            "--callsign", callsign,
            "--role", role,
            "--mission", mission,
            "--sim-time", str(args.sim_time),
            "--live-llm",
            "--temperature", str(args.temperature),
            "--max-tokens", str(args.max_tokens),
            "--seed", str(args.seed),
        ]
        if superior:
            cmd.extend(["--superior", superior])

        if not args.quiet:
            print(f"RUN {callsign} role={role}")

        res = subprocess.run(cmd, check=False)
        if res.returncode == 0:
            ran += 1
        else:
            errors += 1
            print(f"ERROR {callsign} rc={res.returncode}")

    print()
    print(f"SUMMARY ran={ran} errors={errors}")


if __name__ == "__main__":
    main()
