from __future__ import annotations

from pathlib import Path
from typing import Optional

from .redact import redact


def read_head(path: str, max_lines: int = 240) -> str:
    p = Path(path)
    if not p.exists():
        return f"(missing: {path})"
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        return redact("\\n".join(lines[:max_lines]))
    except Exception as e:
        return f"(error reading {path}: {e})"
