from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timezone

from .gitmeta import load_repo_meta, git_status_short, git_log_oneline, RepoMeta
from .fswalk import list_files
from .sections import read_file, FileSection
from .redact import redact_text

@dataclass(frozen=True)
class SnapshotOptions:
    include_tree: bool
    max_tree_files: int
    redact: bool

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def load_repo_meta_wrapper(repo_root: Path) -> RepoMeta:
    return load_repo_meta(repo_root)

# keep old name to match imports in __main__
load_repo_meta = load_repo_meta_wrapper

def _fence(code: str, lang: str = "") -> str:
    # Use triple backticks; do not nest weirdly.
    if lang:
        return f"```{lang}\n{code.rstrip()}\n```"
    return f"```\n{code.rstrip()}\n```"

def _render_file_section(repo_root: Path, sec: FileSection, redact: bool) -> str:
    content = read_file(repo_root, sec.path)
    hdr = f"## FILE: {sec.path}\n"
    if content is None:
        if sec.optional:
            return hdr + "_(missing)_\n"
        return hdr + "_(missing: REQUIRED)_\n"
    if redact:
        content = redact_text(content)
    return hdr + _fence(content) + "\n"

def build_snapshot_markdown(repo_root: Path, profile, include_tree: bool, max_tree_files: int, redact: bool) -> str:
    meta = load_repo_meta(repo_root)
    ts = _now_iso()

    status = git_status_short(repo_root)
    log = git_log_oneline(repo_root, n=20)

    if redact:
        status = redact_text(status)
        log = redact_text(log)

    parts: list[str] = []
    parts.append("# TAKS Chatpack\n")
    parts.append(f"- Generated: {ts}\n")
    parts.append(f"- Repo: {repo_root.name}\n")
    parts.append(f"- Branch: {meta.branch}\n")
    parts.append(f"- Revision: {meta.rev_short}\n\n")
    parts.append("## Intent\n")
    parts.append(profile.intent.strip() + "\n\n")

    parts.append("## Quick status\n")
    parts.append(_fence(status) + "\n\n")

    parts.append("## Recent commits\n")
    parts.append(_fence(log) + "\n\n")

    if include_tree:
        parts.append(f"## Repo tree (top-level, first {max_tree_files} files)\n")
        tree = "\n".join(list_files(repo_root, max_depth=2, limit=max_tree_files))
        parts.append(_fence(tree) + "\n\n")

    # Group by section title
    current_title = None
    for sec in profile.sections:
        if sec.title != current_title:
            parts.append(f"# {sec.title}\n\n")
            current_title = sec.title
        parts.append(_render_file_section(repo_root, sec, redact=redact))

    # Journal pointer
    parts.append("\n# Chatpack journal\n\n")
    parts.append("New chats should add context by writing journal entries:\n\n")
    parts.append(_fence("tools/chatpack-orchestrator append --title \"...\" --text \"...\"") + "\n")

    return "".join(parts)

def write_snapshot(out_path: Path, md: str) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md)

def append_journal_entry(repo_root: Path, title: str, file_rel: str | None, text: str | None, redact: bool) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_title = "".join(ch if ch.isalnum() or ch in ("-", "_") else "-" for ch in title.strip().lower())[:80]
    name = f"{ts}-{safe_title or 'entry'}.md"

    journal_dir = repo_root / "chatpack" / "journal"
    journal_dir.mkdir(parents=True, exist_ok=True)
    p = journal_dir / name

    body: list[str] = []
    body.append(f"# {title}\n\n")
    body.append(f"- Timestamp: {datetime.now(timezone.utc).isoformat(timespec='seconds')}\n\n")

    if text:
        t = text
        if redact:
            t = redact_text(t)
        body.append("## Notes\n\n")
        body.append(t.rstrip() + "\n\n")

    if file_rel:
        content = read_file(repo_root, file_rel) or ""
        if redact:
            content = redact_text(content)
        body.append(f"## FILE: {file_rel}\n\n")
        body.append("```\\\n" + content.rstrip() + "\n```\n")

    p.write_text("".join(body))
    return p
