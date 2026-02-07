from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, Optional, Sequence


@dataclass(frozen=True)
class CotActivity:
    uid: str
    callsign: Optional[str]
    last_time: datetime
    stale: datetime
    is_current: bool


def _rows_to_map(rows: Sequence[Any]) -> Dict[str, CotActivity]:
    """
    DB.fetchall() returns list[tuple] in takctl.infra.db.DB.
    Expected column order:
      username, uid, callsign, time, stale, is_current
    """
    out: Dict[str, CotActivity] = {}
    for r in rows:
        username, uid, callsign, t, stale, is_current = r
        out[username] = CotActivity(
            uid=uid,
            callsign=callsign,
            last_time=t,
            stale=stale,
            is_current=bool(is_current),
        )
    return out


def fetch_activity_for_usernames(db, usernames: Sequence[str]) -> Dict[str, CotActivity]:
    """
    Map XML usernames -> latest CoT activity, via:
      client_endpoint.username -> client_endpoint.uid -> latestcot(uid)
    """
    if not usernames:
        return {}

    sql = """
WITH endpoints AS (
  SELECT username, uid, callsign
  FROM client_endpoint
  WHERE username = ANY(%s)
),
joined AS (
  SELECT
    e.username,
    e.uid,
    e.callsign,
    lc.time,
    lc.stale,
    (lc.stale > now()) AS is_current
  FROM endpoints e
  JOIN latestcot lc ON lc.uid = e.uid
),
ranked AS (
  SELECT *,
         row_number() OVER (PARTITION BY username ORDER BY time DESC NULLS LAST) AS rn
  FROM joined
)
SELECT username, uid, callsign, time, stale, is_current
FROM ranked
WHERE rn = 1;
"""
    rows = db.fetchall(sql, (list(usernames),))
    return _rows_to_map(rows)


def fetch_unknown_endpoints(db, known_usernames: Iterable[str], limit: int = 50) -> list[dict[str, Any]]:
    """
    Find usernames that have CoT activity but are not present in the authoritative UserDirectory (XML).
    Uses client_endpoint + latestcot, picks newest activity per client_endpoint.username.
    """
    known = set(known_usernames)

    sql = """
WITH joined AS (
  SELECT
    ce.username,
    ce.callsign,
    ce.uid,
    lc.time,
    lc.stale,
    (lc.stale > now()) AS is_current,
    row_number() OVER (PARTITION BY ce.username ORDER BY lc.time DESC NULLS LAST) AS rn
  FROM client_endpoint ce
  JOIN latestcot lc ON lc.uid = ce.uid
)
SELECT username, callsign, uid, time, stale, is_current
FROM joined
WHERE rn = 1
ORDER BY time DESC NULLS LAST
LIMIT %s;
"""
    rows = db.fetchall(sql, (int(limit),))
    out: list[dict[str, Any]] = []
    for r in rows:
        username, callsign, uid, t, stale, is_current = r
        if username in known:
            continue
        out.append(
            {
                "username": username,
                "callsign": callsign,
                "uid": uid,
                "last_cot_time": t,
                "stale": stale,
                "is_current": bool(is_current),
            }
        )
    return out
