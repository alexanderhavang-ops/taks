from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _atomic_write(path: Path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(data, encoding="utf-8")
    tmp.replace(path)


def write_json(path: Path, obj: Any) -> None:
    _atomic_write(path, json.dumps(obj, indent=2, sort_keys=True) + "\n")


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"ok": False, "error": "not_found", "path": str(path)}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"ok": False, "error": f"read_failed: {type(e).__name__}: {e}", "path": str(path)}
