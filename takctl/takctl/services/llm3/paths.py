from __future__ import annotations

from pathlib import Path


def state_root() -> Path:
    return Path('/opt/tak/tools/takctl/state/llm3')


def latest_root() -> Path:
    return state_root() / 'latest'


def runs_root() -> Path:
    return state_root() / 'runs'
