from __future__ import annotations

import json
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any


def _json_default(o: Any):
    # datetime/date/time -> ISO 8601 strings
    if isinstance(o, (datetime, date, time)):
        try:
            return o.isoformat()
        except Exception:
            return str(o)

    # Decimal -> float (or str if you prefer strictness later)
    if isinstance(o, Decimal):
        return float(o)

    # Path -> string
    if isinstance(o, Path):
        return str(o)

    # bytes -> utf-8 best-effort
    if isinstance(o, (bytes, bytearray)):
        try:
            return o.decode("utf-8", "replace")
        except Exception:
            return str(o)

    # fallback
    return str(o)


def _atomic_write(path: Path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(data, encoding="utf-8")
    tmp.replace(path)


def write_json(path: Path, obj: Any) -> None:
    _atomic_write(path, json.dumps(obj, indent=2, sort_keys=True, default=_json_default) + "\n")


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"ok": False, "error": "not_found", "path": str(path)}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"ok": False, "error": f"read_failed: {type(e).__name__}: {e}", "path": str(path)}
