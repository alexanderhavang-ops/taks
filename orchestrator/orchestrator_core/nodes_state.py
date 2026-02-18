from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


def _state_dir() -> Path:
    return Path(os.environ.get("TAKS_STATE_DIR") or "/opt/tak-orch/state")


def nodes_dir() -> Path:
    d = _state_dir() / "nodes"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _now() -> int:
    return int(time.time())


def _read_json(p: Path) -> Dict[str, Any]:
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def _write_json(p: Path, d: Dict[str, Any]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def node_path(node_id: str) -> Path:
    safe = (node_id or "").strip()
    if not safe:
        raise ValueError("node_id required")
    return nodes_dir() / f"{safe}.json"


def upsert_node(node_id: str, patch: Dict[str, Any]) -> Dict[str, Any]:
    p = node_path(node_id)
    cur = _read_json(p) or {}
    cur.setdefault("node_id", node_id)
    cur.setdefault("created_ts", _now())
    cur["updated_ts"] = _now()
    cur.update({k: v for k, v in patch.items() if v is not None})
    _write_json(p, cur)
    return cur


def touch_heartbeat(node_id: str, status: str = "online", extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    patch: Dict[str, Any] = {
        "last_seen_ts": _now(),
        "status": status,
    }
    if extra:
        patch.update(extra)
    return upsert_node(node_id, patch)


def list_nodes() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    d = nodes_dir()
    for p in sorted(d.glob("*.json")):
        try:
            out.append(_read_json(p))
        except Exception:
            # don't brick listing because one file is bad
            out.append({"node_id": p.stem, "error": "invalid_json", "path": str(p)})
    # newest activity first
    out.sort(key=lambda x: int(x.get("last_seen_ts") or x.get("updated_ts") or 0), reverse=True)
    return out
