from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional, Sequence


@dataclass(frozen=True)
class CotActivity:
    uid: str
    callsign: Optional[str]
    last_time: datetime
    stale: Optional[datetime]
    is_current: bool


def _to_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _age_human(seconds: int) -> str:
    if seconds < 0:
        seconds = 0
    m, _ = divmod(seconds, 60)
    h, m = divmod(m, 60)
    d, h = divmod(h, 24)
    if d:
        return f"{d}d{h}h"
    if h:
        return f"{h}h{m}m"
    return f"{m}m"


def _db_fetchall(db, sql: str, params: tuple) -> list[Any]:
    if db is None:
        return []
    if hasattr(db, "fetchall") and callable(getattr(db, "fetchall")):
        rows = db.fetchall(sql, params)
        return list(rows or [])
    if hasattr(db, "query") and callable(getattr(db, "query")):
        rows = db.query(sql, params)
        return list(rows or [])
    cur = db.cursor()
    cur.execute(sql, params)
    rows = cur.fetchall() or []
    return list(rows)


def _row_get(row: Any, idx: int, key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    return row[idx]


def _sql_in_placeholders(n: int) -> str:
    if n <= 0:
        return "%s"
    return ",".join(["%s"] * n)


def fetch_devices_for_usernames(
    db,
    usernames: Sequence[str],
    *,
    recent_minutes: int = 120,
) -> Dict[str, list[dict[str, Any]]]:
    names = [str(x or "").strip() for x in (usernames or []) if str(x or "").strip()]
    if not names:
        return {}

    ph = _sql_in_placeholders(len(names))
    sql = f"""
WITH latest_event AS (
  SELECT
    e.client_endpoint_id,
    e.created_ts,
    e.connection_event_type_id,
    e.client_version,
    row_number() OVER (
      PARTITION BY e.client_endpoint_id
      ORDER BY e.created_ts DESC, e.id DESC
    ) AS rn
  FROM public.client_endpoint_event e
),
cert_counts AS (
  SELECT
    c.client_uid,
    count(*)::int AS certs_n,
    count(*) FILTER (WHERE c.revocation_date IS NOT NULL)::int AS revoked_certs_n
  FROM public.certificate c
  GROUP BY c.client_uid
)
SELECT
  ce.username,
  ce.id AS endpoint_id,
  ce.callsign AS observed_callsign,
  ce.uid AS client_uid,
  lc.time AS last_cot_time,
  lc.stale AS stale,
  CASE
    WHEN lc.stale IS NULL THEN false
    ELSE (lc.stale > now())
  END AS is_current,
  le.created_ts AS last_event_time,
  le.connection_event_type_id,
  le.client_version,
  COALESCE(cc.certs_n, 0) AS certs_n,
  COALESCE(cc.revoked_certs_n, 0) AS revoked_certs_n
FROM public.client_endpoint ce
LEFT JOIN latestcot lc
  ON lc.uid = ce.uid
LEFT JOIN latest_event le
  ON le.client_endpoint_id = ce.id
 AND le.rn = 1
LEFT JOIN cert_counts cc
  ON cc.client_uid = ce.uid
WHERE ce.username IN ({ph})
ORDER BY
  ce.username,
  lc.time DESC NULLS LAST,
  le.created_ts DESC NULLS LAST,
  ce.id DESC
;
"""
    rows = _db_fetchall(db, sql, tuple(names))
    out: Dict[str, list[dict[str, Any]]] = {}
    now = datetime.now(timezone.utc)

    for row in rows:
        username = str(_row_get(row, 0, "username") or "").strip()
        if not username:
            continue

        endpoint_id = _row_get(row, 1, "endpoint_id")
        observed_callsign = _row_get(row, 2, "observed_callsign")
        client_uid = _row_get(row, 3, "client_uid")
        last_cot_time = _to_utc(_row_get(row, 4, "last_cot_time"))
        stale = _to_utc(_row_get(row, 5, "stale"))
        is_current = bool(_row_get(row, 6, "is_current"))
        last_event_time = _to_utc(_row_get(row, 7, "last_event_time"))
        connection_event_type_id = _row_get(row, 8, "connection_event_type_id")
        client_version = _row_get(row, 9, "client_version")
        certs_n = int(_row_get(row, 10, "certs_n") or 0)
        revoked_certs_n = int(_row_get(row, 11, "revoked_certs_n") or 0)

        cot_seen = last_cot_time is not None
        age_sec = None
        age_human = None
        seen_recently = False
        state = "never"

        if last_cot_time is not None:
            age_sec = int((now - last_cot_time).total_seconds())
            if age_sec < 0:
                age_sec = 0
            age_human = _age_human(age_sec)
            seen_recently = age_sec <= (int(recent_minutes) * 60)
            if is_current:
                state = "current"
            elif seen_recently:
                state = "recent"
            else:
                state = "stale"

        dev = {
            "endpoint_id": endpoint_id,
            "username": username,
            "client_uid": client_uid,
            "observed_callsign": observed_callsign,
            "last_cot_time": last_cot_time.isoformat().replace("+00:00", "Z") if last_cot_time else None,
            "stale": stale.isoformat().replace("+00:00", "Z") if stale else None,
            "is_current": is_current,
            "last_event_time": last_event_time.isoformat().replace("+00:00", "Z") if last_event_time else None,
            "connection_event_type_id": connection_event_type_id,
            "client_version": client_version,
            "certs_n": certs_n,
            "revoked_certs_n": revoked_certs_n,
            "cot_seen": cot_seen,
            "seen_recently": seen_recently,
            "age_sec": age_sec,
            "age_human": age_human,
            "state": state,
        }
        out.setdefault(username, []).append(dev)

    return out


def fetch_devices_for_username(
    db,
    username: str,
    *,
    recent_minutes: int = 120,
) -> list[dict[str, Any]]:
    return fetch_devices_for_usernames(db, [username], recent_minutes=recent_minutes).get(
        str(username or "").strip(),
        [],
    )


def fetch_activity_for_usernames(db, usernames: Sequence[str]) -> Dict[str, CotActivity]:
    devices_map = fetch_devices_for_usernames(db, usernames, recent_minutes=120)
    out: Dict[str, CotActivity] = {}

    for username, devices in devices_map.items():
        best = None
        for d in devices:
            ts = d.get("last_cot_time")
            if not ts:
                continue
            if best is None or str(ts) > str(best.get("last_cot_time") or ""):
                best = d
        if best is None:
            continue

        last_time = best.get("last_cot_time")
        stale = best.get("stale")

        def _from_iso(s: Optional[str]) -> Optional[datetime]:
            if not s:
                return None
            x = str(s)
            if x.endswith("Z"):
                x = x[:-1] + "+00:00"
            dt = datetime.fromisoformat(x)
            return _to_utc(dt)

        last_dt = _from_iso(last_time)
        stale_dt = _from_iso(stale)

        if last_dt is None:
            continue

        out[username] = CotActivity(
            uid=str(best.get("client_uid") or ""),
            callsign=(str(best.get("observed_callsign")) if best.get("observed_callsign") is not None else None),
            last_time=last_dt,
            stale=stale_dt,
            is_current=bool(best.get("is_current")),
        )

    return out


def fetch_unknown_endpoints(
    db,
    known_usernames: Iterable[str],
    *,
    limit: int = 50,
    recent_minutes: int = 120,
) -> list[dict[str, Any]]:
    known = {str(x or "").strip() for x in (known_usernames or []) if str(x or "").strip()}

    sql = """
WITH ranked AS (
  SELECT
    ce.username,
    ce.callsign,
    ce.uid,
    lc.time,
    lc.stale,
    CASE
      WHEN lc.stale IS NULL THEN false
      ELSE (lc.stale > now())
    END AS is_current,
    row_number() OVER (
      PARTITION BY ce.username
      ORDER BY lc.time DESC NULLS LAST, ce.id DESC
    ) AS rn
  FROM public.client_endpoint ce
  JOIN latestcot lc
    ON lc.uid = ce.uid
)
SELECT
  username,
  callsign,
  uid,
  time,
  stale,
  is_current
FROM ranked
WHERE rn = 1
ORDER BY time DESC NULLS LAST
LIMIT %s
;
"""
    rows = _db_fetchall(db, sql, (int(limit),))
    now = datetime.now(timezone.utc)
    out: list[dict[str, Any]] = []

    for row in rows:
        username = str(_row_get(row, 0, "username") or "").strip()
        if not username or username in known:
            continue

        callsign = _row_get(row, 1, "callsign")
        uid = _row_get(row, 2, "uid")
        last_cot_time = _to_utc(_row_get(row, 3, "time"))
        stale = _to_utc(_row_get(row, 4, "stale"))
        is_current = bool(_row_get(row, 5, "is_current"))

        age_sec = None
        age_human = None
        seen_recently = False
        if last_cot_time is not None:
            age_sec = int((now - last_cot_time).total_seconds())
            if age_sec < 0:
                age_sec = 0
            age_human = _age_human(age_sec)
            seen_recently = age_sec <= (int(recent_minutes) * 60)

        out.append(
            {
                "username": username,
                "callsign": callsign,
                "uid": uid,
                "last_cot_time": last_cot_time.isoformat().replace("+00:00", "Z") if last_cot_time else None,
                "stale": stale.isoformat().replace("+00:00", "Z") if stale else None,
                "is_current": is_current,
                "age_sec": age_sec,
                "age_human": age_human,
                "seen_recently": seen_recently,
            }
        )

    return out
