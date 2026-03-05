from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List

# NOTE: Keep consistent with other state modules
def _state_dir() -> Path:
    return Path(os.environ.get("TAKS_STATE_DIR") or "/opt/tak-orch/state")


def _units_dir() -> Path:
    return _state_dir() / "units"


def _safe_unit_path(unit_path: str) -> str:
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


def materialize_overlay_units(default_title_prefix: str = "") -> int:
    """
    Ensure overlay-only units become real units with unit.json.

    If units/<unit>/bundle/overlay/ exists but unit.json does not, create unit.json.
    Idempotent and safe to run on every list_units() call.
    """
    ensure_units_dir()
    base = _units_dir()
    now = int(time.time())
    created = 0

    for d in base.rglob("bundle/overlay"):
        if not d.is_dir():
            continue
        try:
            rel = d.relative_to(base)
            parts = rel.parts
            # units/<unit_path>/bundle/overlay
            if len(parts) < 3 or parts[-2:] != ("bundle", "overlay"):
                continue
            up = "/".join(parts[:-2])
            if not up:
                continue

            f = _unit_file(up)
            if f.exists():
                continue

            title = default_title_prefix + up
            obj = {
                "unit_path": up,
                "title": title,
                "parent_path": "",
                "created_ts": now,
                "updated_ts": now,
                "meta": {},
                "overlay_files": _count_overlay_files(up),
            }
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            created += 1
        except Exception:
            continue

    return created


def _overlay_dir(unit_path: str) -> Path:
    # Conventional location for unit bundle overlays
    return _unit_dir(unit_path) / "bundle" / "overlay"


def _count_overlay_files(unit_path: str) -> int:
    d = _overlay_dir(unit_path)
    if not d.exists():
        return 0
    n = 0
    for p in d.rglob("*"):
        if p.is_file():
            n += 1
    return n


def ensure_units_dir() -> None:
    _units_dir().mkdir(parents=True, exist_ok=True)


def create_unit(unit_path: str, title: str = "", parent_path: str = "") -> Dict[str, Any]:
    """
    Create unit.json for unit_path.

    Idempotent: if unit.json exists and parses to a dict with unit_path, return it.
    """
    ensure_units_dir()
    up = _safe_unit_path(unit_path)
    pp = _safe_unit_path(parent_path) if (parent_path or "").strip() else ""

    d = _unit_dir(up)
    d.mkdir(parents=True, exist_ok=True)

    f = _unit_file(up)
    now = int(time.time())

    if f.exists():
        # idempotent create
        try:
            obj = json.loads(f.read_text(encoding="utf-8"))
            if isinstance(obj, dict) and obj.get("unit_path"):
                return obj
        except Exception:
            pass

    obj: Dict[str, Any] = {
        "unit_path": up,
        "title": (title or "").strip(),
        "parent_path": pp,
        "created_ts": now,
        "updated_ts": now,
        "meta": {},
        "overlay_files": _count_overlay_files(up),
    }

    tmp = f.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, f)
    return obj


def update_unit(unit_path: str, title: str | None = None, parent_path: str | None = None, meta: dict | None = None) -> Dict[str, Any]:
    """
    Update unit.json for unit_path.

    - If unit.json exists: load it; else: create a new object.
    - title/parent_path/meta are optional patches; if None, keep existing.
    - updated_ts always bumped.
    - overlay_files always recomputed.
    """
    ensure_units_dir()
    up = _safe_unit_path(unit_path)

    pp: str | None = None
    if parent_path is not None:
        pp = _safe_unit_path(parent_path) if (str(parent_path) or "").strip() else ""

    f = _unit_file(up)
    now = int(time.time())

    obj: Dict[str, Any] = {}
    if f.exists():
        try:
            loaded = json.loads(f.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                obj = loaded
        except Exception:
            obj = {}

    # ensure base schema
    obj["unit_path"] = up
    obj.setdefault("title", "")
    obj.setdefault("parent_path", "")
    obj.setdefault("created_ts", now)
    obj["updated_ts"] = now
    obj.setdefault("meta", {})

    if title is not None:
        obj["title"] = str(title).strip()

    if pp is not None:
        obj["parent_path"] = pp

    if meta is not None:
        obj["meta"] = meta if isinstance(meta, dict) else {}

    obj["overlay_files"] = _count_overlay_files(up)

    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, f)
    return obj


def list_units() -> List[Dict[str, Any]]:
    """
    Returns one row per unit_path under state/units.

    Schema (stable, KISS):
      unit_path
      overlay_files   (count of files under units/<unit>/bundle/overlay/)
      meta            (reserved; always dict)
      + if unit.json exists: title, parent_path, created_ts, updated_ts
    """
    ensure_units_dir()
    # Convert overlay-only units into real unit.json rows
    materialize_overlay_units()

    base = _units_dir()
    out: List[Dict[str, Any]] = []

    if not base.exists():
        return out

    # A unit "exists" if either:
    #  - unit.json exists, OR
    #  - bundle/overlay exists (historical usage)
    seen = set()

    for f in base.rglob("unit.json"):
        try:
            obj = json.loads(f.read_text(encoding="utf-8"))
            if isinstance(obj, dict) and obj.get("unit_path"):
                up = str(obj["unit_path"])
                row = dict(obj)
                # Ensure stable fields even if unit.json is old
                row["meta"] = row.get("meta") if isinstance(row.get("meta"), dict) else {}
                row["overlay_files"] = _count_overlay_files(up)
                out.append(row)
                seen.add(up)
        except Exception:
            continue

    # Also include overlay-only units that have no unit.json yet
    for d in base.rglob("bundle/overlay"):
        try:
            rel = d.relative_to(base)
            parts = rel.parts
            # units/<unit_path>/bundle/overlay
            if len(parts) >= 3 and parts[-3:] == ("bundle", "overlay"):
                up = "/".join(parts[:-2])  # drop bundle/overlay
                if up and up not in seen:
                    out.append(
                        {
                            "unit_path": up,
                            "meta": {},
                            "overlay_files": _count_overlay_files(up),
                        }
                    )
                    seen.add(up)
        except Exception:
            continue

    out.sort(key=lambda x: x.get("unit_path") or "")
    return out
