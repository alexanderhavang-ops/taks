from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STATE_PATH = Path("/opt/tak/tools/martine/state/xmpp_inviter/state.json")


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _iso_from_epoch(value: Any) -> str | None:
    try:
        ts = int(value)
    except Exception:
        return None
    if ts <= 0:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _room_label(room: str) -> str:
    room = str(room or "").strip()
    if not room:
        return ""
    return room.split("@", 1)[0]


def load_openfire_snapshot() -> dict[str, Any]:
    try:
        raw = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}

    if not isinstance(raw, dict):
        return {}

    snap = _as_dict(raw.get("openfire"))
    if snap:
        return snap

    # Fallback for old state.json before martine-xmpp-inviter has written
    # the richer snapshot. This gives invite visibility immediately.
    invites = _as_dict(raw.get("invites"))
    by_username: dict[str, dict[str, Any]] = {}

    for key, ts in invites.items():
        target, sep, room = str(key or "").partition("|")
        if not sep or "@" not in target or not room:
            continue

        username = target.split("@", 1)[0]
        ent = by_username.setdefault(
            username,
            {
                "username": username,
                "jid": target,
                "online": False,
                "status": "unknown",
                "live_jid": "",
                "live_resource": "",
                "rooms": [],
                "room_labels": [],
                "invites": [],
            },
        )

        ent["invites"].append(
            {
                "room": room,
                "room_label": _room_label(room),
                "last_sent_epoch": int(ts or 0) if str(ts or "").isdigit() else 0,
                "last_sent": _iso_from_epoch(ts),
            }
        )

    for ent in by_username.values():
        rooms = sorted({str(x.get("room") or "") for x in ent["invites"] if x.get("room")})
        ent["rooms"] = rooms
        ent["room_labels"] = [_room_label(x) for x in rooms if _room_label(x)]

    return {
        "source": "legacy_invites",
        "state_path": str(STATE_PATH),
        "by_username": by_username,
    }


def openfire_for_username(username: str) -> dict[str, Any] | None:
    u = str(username or "").strip().lower()
    if not u:
        return None

    snap = load_openfire_snapshot()
    by_username = _as_dict(snap.get("by_username"))
    ent = _as_dict(by_username.get(u))
    if not ent:
        return None

    out = dict(ent)
    out.setdefault("source", snap.get("source") or "martine-xmpp-inviter")
    out.setdefault("state_path", str(STATE_PATH))
    return out


def attach_openfire_to_status(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return payload

    users = payload.get("users")
    if not isinstance(users, list):
        return payload

    online_n = 0
    known_n = 0

    for row in users:
        if not isinstance(row, dict):
            continue

        username = ""
        header = row.get("header")
        if isinstance(header, dict):
            username = str(header.get("username") or "").strip()
        if not username:
            username = str(row.get("username") or "").strip()

        of = openfire_for_username(username)
        if not of:
            continue

        row["openfire"] = of
        row["xmpp"] = of
        known_n += 1
        if bool(of.get("online")):
            online_n += 1

    summary = payload.setdefault("summary", {})
    if isinstance(summary, dict):
        summary["openfire_known"] = known_n
        summary["openfire_online"] = online_n

    return payload
