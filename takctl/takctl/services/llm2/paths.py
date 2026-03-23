from __future__ import annotations

from pathlib import Path

from takctl.config import load_config


def runtime_root() -> Path:
    return Path("/opt/tak/tools/takctl")


def infra_root() -> Path:
    return runtime_root() / "llm-infra"


def domains_root() -> Path:
    return infra_root() / "domains"


def state_root() -> Path:
    cfg = load_config()
    return Path(cfg.llm_state_dir) / "llm2"


def runs_root() -> Path:
    return state_root() / "runs"


def latest_root() -> Path:
    return state_root() / "latest"


def latest_run_pointer() -> Path:
    return latest_root() / "run.latest.json"
