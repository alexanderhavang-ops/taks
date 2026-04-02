from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def new_run_id(prefix: str = '') -> str:
    ts = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())
    rnd = uuid.uuid4().hex[:8]
    return f"{prefix + '-' if prefix else ''}{ts}-{rnd}"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class TraceWriter:
    def __init__(self, root: str | Path, run_id: str):
        self.root = Path(root) / run_id
        self.root.mkdir(parents=True, exist_ok=True)
        self.run_id = str(run_id)

    @property
    def path(self) -> Path:
        return self.root

    @property
    def events_path(self) -> Path:
        return self.root / "events.jsonl"

    def write_text(self, name: str, text: str) -> str:
        p = self.root / name
        p.write_text(str(text), encoding='utf-8')
        return str(p)

    def write_json(self, name: str, payload: Any) -> str:
        p = self.root / name
        p.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding='utf-8')
        return str(p)

    def append_event(self, event_type: str, payload: dict[str, Any] | None = None) -> str:
        row: dict[str, Any] = {
            "ts": _utc_now_iso(),
            "run_id": self.run_id,
            "type": str(event_type or "").strip(),
        }
        if payload:
            row.update(payload)

        p = self.events_path
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        return str(p)
