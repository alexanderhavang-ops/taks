from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class ChatpackContext:
    host: str
    ts_utc: str
    llm_url: str
    repo_root: str
    timeout: int = 10
