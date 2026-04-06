from __future__ import annotations

import json
import subprocess
from pathlib import PurePosixPath
from typing import Literal

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api/logs", tags=["logs"])

LOG_ROOT = "/var/log"
HELPER_PATH = "/opt/tak/tools/takctl/bin/takctl-log-helper"
DEFAULT_TAIL_LINES = 1000
MAX_TAIL_LINES = 20000


def _clean_rel_path(raw_path: str | None) -> str:
    if not raw_path or raw_path == "/":
        return ""
    rel = PurePosixPath("/" + str(raw_path).lstrip("/")).as_posix()
    return "" if rel == "/" else rel.lstrip("/")


def _norm_path(raw_path: str | None) -> str:
    rel = _clean_rel_path(raw_path)
    return "/" if not rel else f"/{rel}"


def _raise_from_helper(stderr: str, returncode: int) -> None:
    detail = (stderr or "").strip() or f"log helper failed (rc={returncode})"

    try:
        obj = json.loads(detail)
        if isinstance(obj, dict) and obj.get("error"):
            detail = str(obj["error"])
    except Exception:
        pass

    prefix = detail.split(":", 1)[0].strip()
    status = {
        "FileNotFoundError": 404,
        "NotADirectoryError": 400,
        "IsADirectoryError": 400,
        "ValueError": 400,
        "PermissionError": 403,
    }.get(prefix, 500)

    if "sudo:" in detail.lower():
        status = 500

    raise HTTPException(status_code=status, detail=detail)


def _run_helper(args: list[str]) -> dict:
    cmd = ["sudo", "-n", HELPER_PATH] + args

    try:
        proc = subprocess.run(
            cmd,
            text=True,
            capture_output=True,
            check=False,
            timeout=120,
        )
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=504, detail=f"log helper timed out: {exc}") from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"failed to start log helper: {exc}") from exc

    if proc.returncode != 0:
        _raise_from_helper(proc.stderr, proc.returncode)

    try:
        out = json.loads(proc.stdout)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"log helper returned invalid json: {exc}; stdout={proc.stdout[:400]!r}",
        ) from exc

    if not isinstance(out, dict):
        raise HTTPException(status_code=500, detail="log helper returned non-object json")
    if not out.get("ok", False):
        raise HTTPException(status_code=500, detail=f"log helper returned failure: {out}")

    return out


@router.get("/list")
def list_logs(path: str = Query("/", description="Path relative to /var/log")):
    return _run_helper(["list", _norm_path(path)])


@router.get("/read")
def read_log(
    path: str = Query(..., description="File path relative to /var/log"),
    mode: Literal["tail", "full"] = Query("tail"),
    lines: int = Query(DEFAULT_TAIL_LINES, ge=1, le=MAX_TAIL_LINES),
):
    return _run_helper(
        [
            "read",
            _norm_path(path),
            "--mode",
            mode,
            "--lines",
            str(int(lines)),
        ]
    )
