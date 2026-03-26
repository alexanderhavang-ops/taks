from __future__ import annotations

from pathlib import Path

from martine.config import load_config


def martine_state_dir() -> Path:
    return Path(load_config().state_dir)


def ensure_state_dirs() -> dict[str, str]:
    root = martine_state_dir()
    drafts = root / "drafts"
    cache = root / "cache"
    logs = root / "logs"

    for p in (root, drafts, cache, logs):
        p.mkdir(parents=True, exist_ok=True)

    return {
        "root": str(root),
        "drafts": str(drafts),
        "cache": str(cache),
        "logs": str(logs),
    }
