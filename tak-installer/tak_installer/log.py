from __future__ import annotations

import logging
import os


def get_logger(name: str) -> logging.Logger:
    """
    Minimal logger for tak-installer.

    - Logs to stderr
    - Level defaults to INFO
    """
    level_name = "INFO"
    level = getattr(logging, level_name, logging.INFO)

    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Avoid duplicate handlers if imported multiple times
    if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
        h = logging.StreamHandler()
        h.setLevel(level)
        fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        h.setFormatter(fmt)
        logger.addHandler(h)

    logger.propagate = False
    return logger
