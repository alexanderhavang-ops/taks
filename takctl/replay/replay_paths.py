from __future__ import annotations

from pathlib import Path

SOURCE_ROOT = Path("/opt/taks/takctl/replay")
RUNTIME_ROOT = Path("/opt/tak/replay")

PROMPT_ROOT = SOURCE_ROOT / "prompts"
SEED_ROOT = SOURCE_ROOT / "seeds"

STATE_ROOT = RUNTIME_ROOT / "state" / "agents"
LOG_ROOT = RUNTIME_ROOT / "logs"


def agent_dir(callsign: str) -> Path:
    return STATE_ROOT / str(callsign)


def ensure_runtime_dirs() -> None:
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    LOG_ROOT.mkdir(parents=True, exist_ok=True)
