from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))
if str(SCRIPT_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT.parent))

from replay_paths import STATE_ROOT

ROOT = Path("/opt/tak/tools/takctl/replay")
SAFE_CWD = "/tmp"
VENV_PYTHON = Path("/opt/tak/tools/takctl/.venv/bin/python3")


def _python_cmd() -> str:
    if VENV_PYTHON.exists():
        return str(VENV_PYTHON)
    return sys.executable


def _base_env() -> dict[str, str]:
    env = dict(os.environ)
    existing = env.get("PYTHONPATH", "")
    parts = [p for p in existing.split(":") if p]

    wanted = [
        "/opt/tak/tools/takctl",
        "/opt/tak/tools/martine",
    ]
    for w in reversed(wanted):
        if w in parts:
            parts.remove(w)
        parts.insert(0, w)

    env["PYTHONPATH"] = ":".join(parts)
    return env


def run(cmd: list[str], label: str) -> int:
    print(f"\n## {label}")
    print(" ".join(cmd))
    res = subprocess.run(cmd, check=False, env=_base_env(), cwd=SAFE_CWD)
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

    py = _python_cmd()

    all_callsigns = []
    if STATE_ROOT.exists():
        for d in sorted(STATE_ROOT.iterdir()):
            if d.is_dir() and (d / "state.json").exists():
                all_callsigns.append(d.name.upper())

    if args.blue_callsigns.strip():
        selected_blue = [x.strip().upper() for x in args.blue_callsigns.split(",") if x.strip()]
    else:
        selected_blue = []

    if not all_callsigns:
        print("No replay agents found under runtime state")
        return

    # 1. Poll inbox from real CoT for all seeded agents
    for cs in all_callsigns:
        run([py, str(ROOT / "agent_cot_chat_poll.py"), "--callsign", cs], f"poll {cs}")

    # 2. Referee for blue/red pairs inside observation range
    referee_cmd = [
        py, str(ROOT / "run_referee_once.py"),
        "--sim-time", str(args.sim_time),
        "--temperature", str(args.temperature),
        "--max-tokens", str(args.max_tokens),
        "--seed", str(args.seed),
    ]
    if selected_blue:
        referee_cmd.extend(["--blue-callsigns", ",".join(selected_blue)])
    run(referee_cmd, "run referee")

    # 3. Run blue LLM agents
    llm_cmd = [
        py, str(ROOT / "run_llm_agents_once.py"),
        "--sim-time", str(args.sim_time),
        "--temperature", str(args.temperature),
        "--max-tokens", str(args.max_tokens),
        "--seed", str(args.seed),
    ]
    if selected_blue:
        llm_cmd.extend(["--callsigns", ",".join(selected_blue)])
    run(llm_cmd, "run blue llm agents")

    # 4. Emit outbound CoT for all seeded agents
    for cs in all_callsigns:
        run([py, str(ROOT / "agent_cot_chat_emit.py"), "--from-agent", cs], f"emit {cs}")

    # 5. Poll once more so same-tick emitted orders/reports become visible in agent inboxes
    for cs in all_callsigns:
        run([py, str(ROOT / "agent_cot_chat_poll.py"), "--callsign", cs], f"post-emit poll {cs}")

    print(f"\nDONE sim_time={args.sim_time}")


if __name__ == "__main__":
    main()
