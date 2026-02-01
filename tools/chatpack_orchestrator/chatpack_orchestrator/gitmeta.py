from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import subprocess

@dataclass(frozen=True)
class RepoMeta:
    branch: str
    rev_short: str

def _run(repo_root: Path, args: list[str]) -> str:
    p = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    return (p.stdout or "").strip()

def load_repo_meta(repo_root: Path) -> RepoMeta:
    branch = _run(repo_root, ["rev-parse", "--abbrev-ref", "HEAD"]) or "unknown"
    rev_short = _run(repo_root, ["rev-parse", "--short", "HEAD"]) or "unknown"
    return RepoMeta(branch=branch, rev_short=rev_short)

def git_status_short(repo_root: Path) -> str:
    return _run(repo_root, ["status", "-sb"])

def git_log_oneline(repo_root: Path, n: int = 20) -> str:
    return _run(repo_root, ["--no-pager", "log", "-n", str(n), "--oneline"])
