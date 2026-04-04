from __future__ import annotations

import os
from pathlib import Path

SOURCE_ROOT = Path(os.environ.get("TAK_REPLAY_CODE_ROOT", "/opt/tak/tools/takctl/replay")).resolve()
RUNTIME_ROOT = Path(os.environ.get("TAK_REPLAY_STATE_ROOT", "/opt/tak/replay")).resolve()

PROMPT_ROOT = SOURCE_ROOT / "prompts"
SEED_ROOT = SOURCE_ROOT / "seeds"

STATE_ROOT = RUNTIME_ROOT / "state" / "agents"
LOG_ROOT = RUNTIME_ROOT / "logs"


def agent_dir(callsign: str) -> Path:
    return STATE_ROOT / str(callsign)


def ensure_runtime_dirs() -> None:
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    LOG_ROOT.mkdir(parents=True, exist_ok=True)
