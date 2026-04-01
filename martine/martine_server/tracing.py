from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any


def new_run_id(prefix: str = '') -> str:
    ts = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())
    rnd = uuid.uuid4().hex[:8]
    return f"{prefix + '-' if prefix else ''}{ts}-{rnd}"


class TraceWriter:
    def __init__(self, root: str | Path, run_id: str):
        self.root = Path(root) / run_id
        self.root.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self.root

    def write_text(self, name: str, text: str) -> str:
        p = self.root / name
        p.write_text(str(text), encoding='utf-8')
        return str(p)

    def write_json(self, name: str, payload: Any) -> str:
        p = self.root / name
        p.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding='utf-8')
        return str(p)
