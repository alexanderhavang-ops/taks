from __future__ import annotations

import socket

from fastapi import APIRouter

from takctl import __version__
from takctl.config import load_config

router = APIRouter()


@router.get("/meta")
def meta():
    cfg = load_config()

    # Stable node label for both web + CLI:
    # battalion (logical) -> fqdn -> hostname -> OS hostname
    node = (
        getattr(cfg, "battalion", None)
        or getattr(cfg, "fqdn", None)
        or getattr(cfg, "hostname", None)
        or socket.gethostname()
    )

    return {
        "product": "taks",
        "version": __version__,
        "node": node,
    }
