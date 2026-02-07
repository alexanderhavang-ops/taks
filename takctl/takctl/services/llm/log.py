from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class AgentLog:
    root_dir: Path
    session_id: str

    @property
    def session_dir(self) -> Path:
        return self.root_dir / self.session_id

    def ensure(self) -> None:
        self.session_dir.mkdir(parents=True, exist_ok=True)

    def write_json(self, name: str, obj: Any) -> None:
        self.ensure()
        (self.session_dir / name).write_text(
            json.dumps(obj, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def append_jsonl(self, name: str, obj: Any) -> None:
        self.ensure()
        p = self.session_dir / name
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")

