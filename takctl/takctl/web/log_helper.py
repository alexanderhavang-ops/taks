from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

LOG_ROOT = Path("/var/log").resolve()
DEFAULT_TAIL_LINES = 1000
MAX_TAIL_LINES = 20000
HIDE_SUFFIXES = (".gz", ".xz", ".journal")


def _utc_iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _clean_rel_path(raw_path: str | None) -> str:
    if not raw_path or raw_path == "/":
        return ""
    rel = PurePosixPath("/" + str(raw_path).lstrip("/")).as_posix()
    return "" if rel == "/" else rel.lstrip("/")


def _resolve_under_root(raw_path: str | None) -> tuple[str, Path]:
    rel = _clean_rel_path(raw_path)
    candidate = (LOG_ROOT / rel).resolve()
    if candidate != LOG_ROOT and LOG_ROOT not in candidate.parents:
        raise ValueError("Path escapes /var/log")
    return rel, candidate


def _entry_rel_path(parent_rel: str, name: str) -> str:
    if not parent_rel:
        return f"/{name}"
    return f"/{parent_rel.rstrip('/')}/{name}"


def _hidden_name(name: str) -> bool:
    if name in {".", ".."}:
        return True
    for suf in HIDE_SUFFIXES:
        if name.endswith(suf):
            return True
    return False


def _tail_text_file(path: Path, lines: int) -> str:
    if lines <= 0:
        return ""

    with path.open("rb") as fh:
        fh.seek(0, os.SEEK_END)
        file_size = fh.tell()
        if file_size == 0:
            return ""

        block_size = 8192
        blocks: list[bytes] = []
        newline_count = 0
        cursor = file_size

        while cursor > 0 and newline_count <= lines:
            read_size = min(block_size, cursor)
            cursor -= read_size
            fh.seek(cursor)
            chunk = fh.read(read_size)
            blocks.insert(0, chunk)
            newline_count += chunk.count(b"\n")

        data = b"".join(blocks)
        text = data.decode("utf-8", errors="replace")
        text_lines = text.splitlines()
        return "\n".join(text_lines[-lines:])


def cmd_list(raw_path: str) -> dict:
    parent_rel, target = _resolve_under_root(raw_path)

    if not target.exists():
        raise FileNotFoundError("Path not found")
    if not target.is_dir():
        raise NotADirectoryError("Path is not a directory")

    entries = []
    with os.scandir(target) as it:
        for entry in it:
            name = entry.name
            if _hidden_name(name):
                continue
            if entry.is_symlink():
                continue

            rel_path = _entry_rel_path(parent_rel, name)
            try:
                _, resolved = _resolve_under_root(rel_path)
            except Exception:
                continue

            try:
                st = entry.stat(follow_symlinks=False)
            except OSError:
                continue

            mode = st.st_mode
            if stat.S_ISDIR(mode):
                kind = "dir"
            elif stat.S_ISREG(mode):
                kind = "file"
            else:
                continue

            if resolved != LOG_ROOT and LOG_ROOT not in resolved.parents:
                continue

            entries.append(
                {
                    "name": name,
                    "type": kind,
                    "rel_path": rel_path,
                    "size": st.st_size,
                    "mtime": _utc_iso(st.st_mtime),
                    "is_symlink": False,
                }
            )

    entries.sort(key=lambda item: (0 if item["type"] == "dir" else 1, item["name"].lower()))
    return {
        "ok": True,
        "root": str(LOG_ROOT),
        "path": "/" if not parent_rel else f"/{parent_rel}",
        "entries": entries,
    }


def cmd_read(raw_path: str, mode: str, lines: int) -> dict:
    rel, target = _resolve_under_root(raw_path)

    if not target.exists():
        raise FileNotFoundError("Path not found")
    if not target.is_file():
        raise IsADirectoryError("Path is not a file")
    if target.is_symlink():
        raise ValueError("Symlinks are not supported")
    if _hidden_name(target.name):
        raise ValueError("Hidden/compressed/binary journal files are not shown")

    st = target.stat()
    if mode == "full":
        content = target.read_bytes().decode("utf-8", errors="replace")
        truncated = False
    else:
        content = _tail_text_file(target, lines)
        truncated = st.st_size > len(content.encode("utf-8", errors="replace"))

    return {
        "ok": True,
        "root": str(LOG_ROOT),
        "path": f"/{rel}",
        "mode": mode,
        "lines": lines if mode == "tail" else None,
        "size": st.st_size,
        "mtime": _utc_iso(st.st_mtime),
        "truncated": truncated,
        "content": content,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    ap_list = sub.add_parser("list")
    ap_list.add_argument("path", nargs="?", default="/")

    ap_read = sub.add_parser("read")
    ap_read.add_argument("path")
    ap_read.add_argument("--mode", choices=("tail", "full"), default="tail")
    ap_read.add_argument("--lines", type=int, default=DEFAULT_TAIL_LINES)

    ns = ap.parse_args()

    try:
        if ns.cmd == "list":
            out = cmd_list(ns.path)
        elif ns.cmd == "read":
            lines = max(1, min(int(ns.lines), MAX_TAIL_LINES))
            out = cmd_read(ns.path, ns.mode, lines)
        else:
            raise ValueError(f"Unsupported command: {ns.cmd}")

        print(json.dumps(out, ensure_ascii=False))
        return 0

    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
