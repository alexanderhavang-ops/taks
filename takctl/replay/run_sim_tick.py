from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path("/opt/taks/takctl/replay")


def run(cmd: list[str], label: str) -> int:
    print(f"\n## {label}")
    print(" ".join(cmd))
    res = subprocess.run(cmd, check=False)
    print(f"rc={res.returncode}")
    return res.returncode


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sim-time", type=int, required=True)
    ap.add_argument("--blue-callsigns", default="", help="optional comma-separated subset")
    ap.add_argument("--temperature", type=float, default=0.2)
    ap.add_argument("--max-tokens", type=int, default=800)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    py = sys.executable

    # 1. Import incoming CoT chat for all blue LLM agents that matter this tick.
    # For now: top-down important sample set. Expand later.
    default_poll = ["VQ", "PQ", "QQ", "RQ", "SQ", "TQ"]
    poll_callsigns = default_poll[:]

    if args.blue_callsigns.strip():
        requested = [x.strip().upper() for x in args.blue_callsigns.split(",") if x.strip()]
        poll_callsigns = requested[:]

    for cs in poll_callsigns:
        run([py, str(ROOT / "agent_cot_chat_poll.py"), "--callsign", cs], f"poll {cs}")

    # 2. Run blue LLM agents that actually need decisions.
    llm_cmd = [
        py, str(ROOT / "run_llm_agents_once.py"),
        "--sim-time", str(args.sim_time),
        "--temperature", str(args.temperature),
        "--max-tokens", str(args.max_tokens),
        "--seed", str(args.seed),
    ]
    if args.blue_callsigns.strip():
        llm_cmd.extend(["--callsigns", args.blue_callsigns])

    run(llm_cmd, "run blue llm agents")

    # 3. Emit outbound CoT chat from agents that produced outbox traffic.
    # For now, emit from top set. Expand later.
    emit_callsigns = poll_callsigns[:]
    for cs in emit_callsigns:
        run([py, str(ROOT / "agent_cot_chat_emit.py"), "--from-agent", cs], f"emit {cs}")

    print(f"\nDONE sim_time={args.sim_time}")


if __name__ == "__main__":
    main()
