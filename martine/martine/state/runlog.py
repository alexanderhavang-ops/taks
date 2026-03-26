from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict

from martine.state.paths import ensure_state_dirs


def new_run_id() -> str:
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    rnd = uuid.uuid4().hex[:8]
    return f"{ts}-{rnd}"


def run_dir(run_id: str) -> Path:
    dirs = ensure_state_dirs()
    root = Path(dirs["logs"]) / run_id
    root.mkdir(parents=True, exist_ok=True)
    return root


def write_json(run_id: str, name: str, payload: Dict[str, Any]) -> str:
    p = run_dir(run_id) / name
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return str(p)


def write_text(run_id: str, name: str, text: str) -> str:
    p = run_dir(run_id) / name
    p.write_text(str(text), encoding="utf-8")
    return str(p)
