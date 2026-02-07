from __future__ import annotations

import os
import time
from typing import Any


def env(name: str, default: str) -> str:
    v = (os.environ.get(name) or "").strip()
    return v or default


def now_utc_iso() -> str:
    # RFC3339-ish, stable, no datetime import noise
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def truncate(s: str, max_chars: int) -> str:
    if max_chars <= 0:
        return s
    return s if len(s) <= max_chars else (s[: max_chars - 3] + "...")


def rows_to_json(
    rows: list[tuple],
    *,
    max_rows: int,
    max_cell_chars: int,
) -> list[list[str]]:
    out: list[list[str]] = []
    for r in rows[:max_rows]:
        rr: list[str] = []
        for cell in r:
            s = "" if cell is None else str(cell)
            rr.append(truncate(s, max_cell_chars))
        out.append(rr)
    return out

