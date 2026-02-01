from __future__ import annotations
import argparse
import sys
from pathlib import Path

from .core import build_snapshot_markdown, write_snapshot, append_journal_entry, load_repo_meta
from .profiles import get_profile
from .io_utils import eprint

def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="chatpack-orchestrator")
    ap.add_argument("--repo-root", default=".", help="Repo root (default: .)")
    ap.add_argument("--profile", default="orchestrator", help="Profile/scope (default: orchestrator)")
    ap.add_argument("--out", default="chatpack/latest.md", help="Snapshot output path (default: chatpack/latest.md)")

    sub = ap.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate", help="Generate a snapshot markdown file")
    g.add_argument("--include-tree", action="store_true", help="Include a compact repo tree")
    g.add_argument("--max-tree-files", type=int, default=200, help="Max files shown in tree (default: 200)")
    g.add_argument("--no-redact", action="store_true", help="Disable redaction filter (not recommended)")

    j = sub.add_parser("append", help="Append a journal entry (so new chats can add context over time)")
    j.add_argument("--title", required=True, help="Short title for the entry")
    j.add_argument("--file", default="", help="Optional file to include verbatim (relative to repo root)")
    j.add_argument("--text", default="", help="Optional free-form text for the entry")
    j.add_argument("--no-redact", action="store_true", help="Disable redaction filter (not recommended)")

    p = sub.add_parser("print", help="Print snapshot to stdout (useful for piping)")
    p.add_argument("--include-tree", action="store_true", help="Include a compact repo tree")
    p.add_argument("--max-tree-files", type=int, default=200, help="Max files shown in tree (default: 200)")
    p.add_argument("--no-redact", action="store_true", help="Disable redaction filter (not recommended)")

    args = ap.parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    profile = get_profile(args.profile)

    if args.cmd in ("generate", "print"):
        redact = not getattr(args, "no_redact", False)
        md = build_snapshot_markdown(
            repo_root=repo_root,
            profile=profile,
            include_tree=getattr(args, "include_tree", False),
            max_tree_files=getattr(args, "max_tree_files", 200),
            redact=redact,
        )
        if args.cmd == "print":
            sys.stdout.write(md)
            return
        out = repo_root / args.out
        write_snapshot(out, md)
        meta = load_repo_meta(repo_root)
        eprint(f"wrote {out} (rev={meta.rev_short} branch={meta.branch})")
        return

    if args.cmd == "append":
        redact = not getattr(args, "no_redact", False)
        file_rel = getattr(args, "file", "").strip()
        text = getattr(args, "text", "").strip()
        title = getattr(args, "title", "").strip()
        entry_path = append_journal_entry(
            repo_root=repo_root,
            title=title,
            file_rel=file_rel or None,
            text=text or None,
            redact=redact,
        )
        eprint(f"appended journal entry: {entry_path}")
        return

if __name__ == "__main__":
    main()
