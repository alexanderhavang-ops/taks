from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# NOTE: Keep consistent with other state modules
def _state_dir() -> Path:
    return Path(os.environ.get("TAKS_STATE_DIR") or "/opt/tak-orch/state")

def _units_dir() -> Path:
    return _state_dir() / "units"

def _safe_unit_path(unit_path: str) -> str:
    """
    unit_path is a logical path like:
      "46hvbat" or "46hvbat/460" or "46hvbat/ledplut"
    We store it under state/units/<unit_path>/unit.json

    Rules:
      - no empty segments
      - no '.' or '..' segments
      - no backslashes
    """
    up = (unit_path or "").strip().strip("/")
    if not up:
        raise ValueError("missing unit_path")
    if "\\" in up:
        raise ValueError("invalid unit_path: backslash not allowed")
    parts = [p for p in up.split("/") if p]
    for p in parts:
        if p in (".", ".."):
            raise ValueError("invalid unit_path segment")
    return "/".join(parts)

def _unit_dir(unit_path: str) -> Path:
    up = _safe_unit_path(unit_path)
    return _units_dir() / up

def _unit_file(unit_path: str) -> Path:
    return _unit_dir(unit_path) / "unit.json"

def ensure_units_dir() -> None:
    _units_dir().mkdir(parents=True, exist_ok=True)

def create_unit(unit_path: str, title: str = "", parent_path: str = "") -> Dict[str, Any]:
    ensure_units_dir()
    up = _safe_unit_path(unit_path)
    pp = _safe_unit_path(parent_path) if (parent_path or "").strip() else ""

    d = _unit_dir(up)
    d.mkdir(parents=True, exist_ok=True)

    f = _unit_file(up)
    now = int(time.time())

    if f.exists():
        # Do NOT overwrite existing; treat as idempotent create
        obj = json.loads(f.read_text(encoding="utf-8"))
        if isinstance(obj, dict):
            return obj

    obj: Dict[str, Any] = {
        "unit_path": up,
        "title": (title or "").strip(),
        "parent_path": pp,
        "created_ts": now,
        "updated_ts": now,
    }

    tmp = f.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, f)
    return obj

def list_units() -> List[Dict[str, Any]]:
    ensure_units_dir()
    base = _units_dir()
    out: List[Dict[str, Any]] = []

    if not base.exists():
        return out

    for f in base.rglob("unit.json"):
        try:
            obj = json.loads(f.read_text(encoding="utf-8"))
            if isinstance(obj, dict) and obj.get("unit_path"):
                out.append(obj)
        except Exception:
            # ignore broken files (don't brick listing)
            continue

    out.sort(key=lambda x: x.get("unit_path") or "")
    return out
