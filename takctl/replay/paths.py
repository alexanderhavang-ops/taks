from __future__ import annotations

import os
from pathlib import Path

REPLAY_CODE_ROOT = Path("/opt/tak/tools/takctl/replay").resolve()

REPLAY_STATE_ROOT = Path("/opt/tak/replay").resolve()


def replay_code_root() -> Path:
    return REPLAY_CODE_ROOT


def replay_state_root() -> Path:
    return REPLAY_STATE_ROOT


def replay_agents_root() -> Path:
    return REPLAY_STATE_ROOT / "state" / "agents"


def replay_logs_root() -> Path:
    return REPLAY_STATE_ROOT / "logs"


def replay_ui_state_path() -> Path:
    return REPLAY_STATE_ROOT / "ui_state.json"


def replay_prompts_root() -> Path:
    return REPLAY_CODE_ROOT / "prompts"


def replay_seeds_root() -> Path:
    return REPLAY_CODE_ROOT / "seeds"


def ensure_replay_state_dirs() -> None:
    replay_state_root().mkdir(parents=True, exist_ok=True)
    (replay_state_root() / "state").mkdir(parents=True, exist_ok=True)
    replay_agents_root().mkdir(parents=True, exist_ok=True)
    replay_logs_root().mkdir(parents=True, exist_ok=True)
