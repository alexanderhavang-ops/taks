from __future__ import annotations

from dataclasses import dataclass

from takctl.config import load_config


@dataclass(frozen=True)
class AppContext:
    cfg: object


def get_ctx() -> AppContext:
    cfg = load_config()
    return AppContext(cfg=cfg)
