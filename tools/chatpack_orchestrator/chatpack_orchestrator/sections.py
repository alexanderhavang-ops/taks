from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class FileSection:
    title: str
    path: str  # repo-relative path
    optional: bool = True

def read_file(repo_root: Path, rel: str) -> str | None:
    p = (repo_root / rel).resolve()
    try:
        if not p.exists() or not p.is_file():
            return None
        # keep it simple: text read, replacing errors
        return p.read_text(errors="replace")
    except Exception:
        return None
