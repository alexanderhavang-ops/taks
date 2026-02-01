from __future__ import annotations
from pathlib import Path

def list_files(repo_root: Path, max_depth: int = 2, limit: int = 200) -> list[str]:
    out: list[str] = []
    root = repo_root.resolve()

    def depth(p: Path) -> int:
        try:
            return len(p.relative_to(root).parts)
        except Exception:
            return 999

    for p in sorted(root.rglob("*")):
        if p.is_dir():
            continue
        if ".git" in p.parts:
            continue
        if depth(p) > max_depth:
            continue
        rel = str(p.relative_to(root))
        out.append(rel)
        if len(out) >= limit:
            break
    return out
