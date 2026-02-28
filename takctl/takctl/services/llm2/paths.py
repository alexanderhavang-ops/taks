from __future__ import annotations

import os
from pathlib import Path


def runtime_root() -> Path:
    return Path("/opt/tak/tools/takctl")


def infra_root() -> Path:
    # installer-owned deployment target
    return runtime_root() / "llm-infra"


def domains_root() -> Path:
    return infra_root() / "domains"


def state_root() -> Path:
    base = (os.environ.get("TAKCTL_STATE_DIR") or "").strip() or "/opt/tak/tools/takctl/state"
    return Path(base) / "llm2"


def runs_root() -> Path:
    return state_root() / "runs"


def latest_root() -> Path:
    return state_root() / "latest"


def latest_run_pointer() -> Path:
    return latest_root() / "run.latest.json"
