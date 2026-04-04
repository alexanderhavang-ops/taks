from __future__ import annotations

import os
import stat
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Literal

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api/logs", tags=["logs"])

LOG_ROOT = Path("/var/log").resolve()
DEFAULT_TAIL_LINES = 1000
MAX_TAIL_LINES = 20000


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
        raise HTTPException(status_code=400, detail="Path escapes /var/log")
    return rel, candidate


def _entry_rel_path(parent_rel: str, name: str) -> str:
    if not parent_rel:
        return f"/{name}"
    return f"/{parent_rel.rstrip('/')}/{name}"


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


@router.get("/list")
def list_logs(path: str = Query("/", description="Path relative to /var/log")):
    parent_rel, target = _resolve_under_root(path)

    if not target.exists():
        raise HTTPException(status_code=404, detail="Path not found")
    if not target.is_dir():
        raise HTTPException(status_code=400, detail="Path is not a directory")

    entries = []
    try:
        with os.scandir(target) as it:
            for entry in it:
                if entry.name in {".", ".."}:
                    continue
                if entry.name.endswith(".gz"):
                    continue

                rel_path = _entry_rel_path(parent_rel, entry.name)
                try:
                    _, resolved = _resolve_under_root(rel_path)
                except HTTPException:
                    continue

                try:
                    st = entry.stat(follow_symlinks=True)
                except OSError:
                    continue

                mode = st.st_mode
                if stat.S_ISDIR(mode):
                    kind = "dir"
                elif stat.S_ISREG(mode):
                    kind = "file"
                else:
                    continue

                entries.append(
                    {
                        "name": entry.name,
                        "type": kind,
                        "rel_path": rel_path,
                        "size": st.st_size,
                        "mtime": _utc_iso(st.st_mtime),
                        "is_symlink": entry.is_symlink(),
                    }
                )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=f"Permission denied: {exc}") from exc

    entries.sort(key=lambda item: (0 if item["type"] == "dir" else 1, item["name"].lower()))

    return {
        "ok": True,
        "root": str(LOG_ROOT),
        "path": "/" if not parent_rel else f"/{parent_rel}",
        "entries": entries,
    }


@router.get("/read")
def read_log(
    path: str = Query(..., description="File path relative to /var/log"),
    mode: Literal["tail", "full"] = Query("tail"),
    lines: int = Query(DEFAULT_TAIL_LINES, ge=1, le=MAX_TAIL_LINES),
):
    rel, target = _resolve_under_root(path)

    if not target.exists():
        raise HTTPException(status_code=404, detail="Path not found")
    if not target.is_file():
        raise HTTPException(status_code=400, detail="Path is not a file")
    if target.name.endswith(".gz"):
        raise HTTPException(status_code=400, detail="Compressed files are hidden")

    try:
        st = target.stat()
        if mode == "full":
            content = target.read_text(encoding="utf-8", errors="replace")
            truncated = False
        else:
            content = _tail_text_file(target, lines)
            truncated = st.st_size > len(content.encode("utf-8", errors="replace"))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=f"Permission denied: {exc}") from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Read failed: {exc}") from exc

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
