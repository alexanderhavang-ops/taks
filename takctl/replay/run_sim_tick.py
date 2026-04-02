from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path("/opt/tak/tools/takctl/replay")


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

    default_blue = ["AT1", "EAT1", "FAT1", "GAT1", "HAT1"]
    blue_callsigns = default_blue[:]

    if args.blue_callsigns.strip():
        blue_callsigns = [x.strip().upper() for x in args.blue_callsigns.split(",") if x.strip()]

    # 1. Poll blue inbox from real CoT
    for cs in blue_callsigns:
        run([py, str(ROOT / "agent_cot_chat_poll.py"), "--callsign", cs], f"poll {cs}")

    # 2. Referee for blue/red pairs inside observation range
    referee_cmd = [
        py, str(ROOT / "run_referee_once.py"),
        "--sim-time", str(args.sim_time),
        "--temperature", str(args.temperature),
        "--max-tokens", str(args.max_tokens),
        "--seed", str(args.seed),
    ]
    if args.blue_callsigns.strip():
        referee_cmd.extend(["--blue-callsigns", args.blue_callsigns])
    run(referee_cmd, "run referee")

    # 3. Run blue LLM agents
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

    # 4. Emit outbound CoT from blue only
    for cs in blue_callsigns:
        run([py, str(ROOT / "agent_cot_chat_emit.py"), "--from-agent", cs], f"emit {cs}")

    # 5. Poll once more so same-tick emitted orders/reports become visible in agent inboxes
    for cs in blue_callsigns:
        run([py, str(ROOT / "agent_cot_chat_poll.py"), "--callsign", cs], f"post-emit poll {cs}")

    print(f"\nDONE sim_time={args.sim_time}")


if __name__ == "__main__":
    main()
