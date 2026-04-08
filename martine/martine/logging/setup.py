from __future__ import annotations

import logging
import os
from pathlib import Path

_LOG_PATH = Path("/var/log/martine.log")
_FALLBACK_PATH = Path("/opt/tak/tools/martine/state/logs/martine.log")
_CONFIGURED = False


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _pick_log_path() -> Path:
    try:
        _ensure_parent(_LOG_PATH)
        if not _LOG_PATH.exists():
            _LOG_PATH.touch()
        with _LOG_PATH.open("a", encoding="utf-8"):
            pass
        return _LOG_PATH
    except Exception:
        _ensure_parent(_FALLBACK_PATH)
        if not _FALLBACK_PATH.exists():
            _FALLBACK_PATH.touch()
        return _FALLBACK_PATH


def setup_martine_logging() -> Path:
    global _CONFIGURED
    if _CONFIGURED:
        return _pick_log_path()

    path = _pick_log_path()

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    already = False
    for h in root.handlers:
        if getattr(h, "_martine_file_handler", False):
            already = True
            break

    if not already:
        fh = logging.FileHandler(path, encoding="utf-8")
        fh._martine_file_handler = True  # type: ignore[attr-defined]
        fh.setLevel(logging.INFO)
        fh.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s %(name)s pid=%(process)d %(message)s"
            )
        )
        root.addHandler(fh)

    _CONFIGURED = True
    logging.getLogger(__name__).info("martine logging ready path=%s", path)
    return path


def get_logger(name: str) -> logging.Logger:
    setup_martine_logging()
    return logging.getLogger(name)
