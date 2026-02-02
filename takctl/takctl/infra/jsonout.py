from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime
from typing import Any


def _default(o: Any) -> Any:
    if is_dataclass(o):
        return asdict(o)
    if isinstance(o, datetime):
        return o.isoformat()
    if isinstance(o, set):
        return sorted(list(o))
    return str(o)


def dumps(obj: Any) -> str:
    return json.dumps(obj, default=_default, ensure_ascii=False, indent=2, sort_keys=True)


def print_json(console, obj: Any) -> None:
    console.print(dumps(obj))
