from __future__ import annotations

from dataclasses import is_dataclass, asdict
from datetime import datetime
from typing import Any


def _iso(dt: Any) -> str | None:
    if dt is None:
        return None
    if isinstance(dt, datetime):
        return dt.isoformat()
    # strings already OK (psql_sudo mode may return strings)
    return str(dt)


def _as_dict(x: Any) -> dict:
    if is_dataclass(x):
        return asdict(x)
    if isinstance(x, dict):
        return x
    raise TypeError(f"Cannot convert to dict: {type(x)}")


# -------------------------
# Clients
# -------------------------

def clients_list_response(clients: list[Any]) -> dict:
    """
    Canonical JSON schema for clients list.

    {
      "count": <int>,
      "clients": [
        {"callsign": "...", "uid": "...", "last_seen": "<iso>"},
        ...
      ]
    }
    """
    out = []
    for c in clients:
        d = _as_dict(c)
        out.append(
            {
                "callsign": d.get("callsign"),
                "uid": d.get("uid"),
                "last_seen": _iso(d.get("last_seen")),
            }
        )
    return {"count": len(out), "clients": out}

