from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
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


_TAKV_RE = re.compile(r"<takv\b([^>]*)/?>", re.IGNORECASE | re.DOTALL)
_TAKV_ATTR_RE = re.compile(r'([A-Za-z0-9_:-]+)="([^"]*)"')


def _parse_takv_detail(detail: Any) -> dict[str, str]:
    s = str(detail or "")
    if not s or "<takv" not in s.lower():
        return {}
    m = _TAKV_RE.search(s)
    if not m:
        return {}
    attrs: dict[str, str] = {}
    for k, v in _TAKV_ATTR_RE.findall(m.group(1) or ""):
        key = str(k or "").strip().lower()
        val = str(v or "").strip()
        if key:
            attrs[key] = val
    return attrs


def _coalesce_text(*vals: Any) -> Optional[str]:
    for v in vals:
        x = str(v or "").strip()
        if x:
            return x
    return None


def _format_client_product(platform: Any, version: Any) -> Optional[str]:
    p = _coalesce_text(platform)
    v = _coalesce_text(version)
    if p and v:
        return f"{p} {v}"
    return p or v


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
    sql = f'''
WITH names(username) AS (
  SELECT unnest(ARRAY[{ph}]::text[]) AS username
),
latest_event AS (
  SELECT
    e.client_endpoint_id,
    e.created_ts,
    e.connection_event_type_id,
    e.client_version,
    row_number() OVER (
      PARTITION BY e.client_endpoint_id
      ORDER BY e.created_ts DESC NULLS LAST, e.id DESC
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
),
endpoint_candidates AS (
  SELECT
    n.username AS attributed_username,
    ce.id AS endpoint_id,
    ce.callsign AS endpoint_callsign,
    ce.uid AS client_uid,
    NULLIF(ce.username, '') AS endpoint_username,
    'endpoint_username'::text AS attribution_source
  FROM names n
  JOIN public.client_endpoint ce
    ON ce.username = n.username

  UNION ALL

  SELECT
    n.username AS attributed_username,
    ce.id AS endpoint_id,
    ce.callsign AS endpoint_callsign,
    ce.uid AS client_uid,
    NULLIF(ce.username, '') AS endpoint_username,
    'certificate_identity'::text AS attribution_source
  FROM names n
  JOIN public.certificate c
    ON (
      c.user_dn = n.username
      OR c.creator_dn = n.username
      OR EXISTS (
        SELECT 1
        FROM unnest(string_to_array(coalesce(c.subject_dn, ''), ',')) AS dn_part(part)
        WHERE lower(btrim(dn_part.part)) = lower('CN=' || n.username)
      )
    )
  JOIN public.client_endpoint ce
    ON ce.uid = c.client_uid

  UNION ALL

  SELECT
    n.username AS attributed_username,
    ce.id AS endpoint_id,
    ce.callsign AS endpoint_callsign,
    ce.uid AS client_uid,
    NULLIF(ce.username, '') AS endpoint_username,
    'latestcot_xmpp_username'::text AS attribution_source
  FROM names n
  JOIN public.latestcot lc
    ON (
      lc.detail ILIKE ('%%xmppUsername="' || n.username || '@%%')
      OR lc.detail ILIKE ('%%xmppUsername="' || n.username || '"%%')
    )
  JOIN public.client_endpoint ce
    ON ce.uid = lc.uid
),
endpoint_candidates_dedup AS (
  SELECT DISTINCT ON (attributed_username, endpoint_id)
    attributed_username,
    endpoint_id,
    endpoint_callsign,
    client_uid,
    endpoint_username,
    attribution_source
  FROM endpoint_candidates
  ORDER BY
    attributed_username,
    endpoint_id,
    CASE attribution_source
      WHEN 'endpoint_username' THEN 1
      WHEN 'latestcot_xmpp_username' THEN 2
      WHEN 'certificate_identity' THEN 3
      ELSE 9
    END
)
SELECT
  ec.attributed_username AS username,
  ec.endpoint_id,
  ec.endpoint_callsign AS observed_callsign,
  ec.client_uid,
  ec.endpoint_username,
  ec.attribution_source,
  lc.time AS last_cot_time,
  lc.stale AS stale,
  CASE
    WHEN lc.stale IS NULL THEN false
    ELSE (lc.stale > now())
  END AS is_current,
  le.created_ts AS last_event_time,
  le.connection_event_type_id,
  cet.event_name AS connection_event_name,
  le.client_version AS event_client_version,
  lc.detail AS cot_detail,
  COALESCE(cc.certs_n, 0) AS certs_n,
  COALESCE(cc.revoked_certs_n, 0) AS revoked_certs_n
FROM endpoint_candidates_dedup ec
LEFT JOIN public.latestcot lc
  ON lc.uid = ec.client_uid
LEFT JOIN latest_event le
  ON le.client_endpoint_id = ec.endpoint_id
 AND le.rn = 1
LEFT JOIN public.connection_event_type cet
  ON cet.id = le.connection_event_type_id
LEFT JOIN cert_counts cc
  ON cc.client_uid = ec.client_uid
ORDER BY
  ec.attributed_username,
  ec.client_uid,
  lc.time DESC NULLS LAST,
  le.created_ts DESC NULLS LAST,
  ec.endpoint_id DESC
;
'''
    rows = _db_fetchall(db, sql, tuple(names))
    now = datetime.now(timezone.utc)

    def _detail_attrs(detail: Any, tag: str) -> dict[str, str]:
        s = str(detail or "")
        if not s:
            return {}
        m = re.search(r"<" + re.escape(tag) + r"\b([^>]*)/?>", s, re.IGNORECASE | re.DOTALL)
        if not m:
            return {}
        attrs: dict[str, str] = {}
        for k, v in _TAKV_ATTR_RE.findall(m.group(1) or ""):
            key = str(k or "").strip().lower()
            val = str(v or "").strip()
            if key:
                attrs[key] = val
        return attrs

    def _callsign_from_detail(detail: Any) -> Optional[str]:
        contact = _detail_attrs(detail, "contact")
        cs = _coalesce_text(contact.get("callsign"))
        if cs:
            return cs
        uid_tag = _detail_attrs(detail, "uid")
        return _coalesce_text(uid_tag.get("droid"))

    def _add_unique(out_list: list[str], seen: set[str], value: Any) -> None:
        v = str(value or "").strip()
        if not v:
            return
        key = v.upper()
        if key in seen:
            return
        seen.add(key)
        out_list.append(v)

    candidates: dict[tuple[str, str], list[dict[str, Any]]] = {}

    for row in rows:
        username = str(_row_get(row, 0, "username") or "").strip()
        client_uid = str(_row_get(row, 3, "client_uid") or "").strip()
        if not username or not client_uid:
            continue

        last_cot_time = _to_utc(_row_get(row, 6, "last_cot_time"))
        stale = _to_utc(_row_get(row, 7, "stale"))
        last_event_time = _to_utc(_row_get(row, 9, "last_event_time"))
        cot_detail = _row_get(row, 13, "cot_detail")

        takv = _parse_takv_detail(cot_detail)
        tak_platform = _coalesce_text(takv.get("platform"))
        tak_version = _coalesce_text(takv.get("version"), _row_get(row, 12, "event_client_version"))
        tak_device = _coalesce_text(takv.get("device"))
        tak_os = _coalesce_text(takv.get("os"))
        client_version = _coalesce_text(tak_version, _row_get(row, 12, "event_client_version"))
        client_product = _format_client_product(tak_platform, tak_version)

        candidates.setdefault((username, client_uid), []).append(
            {
                "endpoint_id": _row_get(row, 1, "endpoint_id"),
                "username": username,
                "client_uid": client_uid,
                "observed_callsign": _row_get(row, 2, "observed_callsign"),
                "endpoint_username": _row_get(row, 4, "endpoint_username"),
                "attribution_source": _row_get(row, 5, "attribution_source"),
                "last_cot_time_dt": last_cot_time,
                "stale_dt": stale,
                "is_current": bool(_row_get(row, 8, "is_current")),
                "last_event_time_dt": last_event_time,
                "connection_event_type_id": _row_get(row, 10, "connection_event_type_id"),
                "connection_event_name": _row_get(row, 11, "connection_event_name"),
                "event_client_version": _row_get(row, 12, "event_client_version"),
                "cot_detail": cot_detail,
                "current_callsign_from_cot": _callsign_from_detail(cot_detail),
                "client_version": client_version,
                "client_platform": tak_platform,
                "client_product": client_product,
                "tak_platform": tak_platform,
                "tak_version": tak_version,
                "tak_device": tak_device,
                "tak_os": tak_os,
                "certs_n": int(_row_get(row, 14, "certs_n") or 0),
                "revoked_certs_n": int(_row_get(row, 15, "revoked_certs_n") or 0),
            }
        )

    out: Dict[str, list[dict[str, Any]]] = {}

    for (username, client_uid), items in candidates.items():
        items.sort(
            key=lambda d: (
                1 if d.get("is_current") else 0,
                d.get("last_event_time_dt") or datetime.min.replace(tzinfo=timezone.utc),
                int(d.get("endpoint_id") or 0),
            ),
            reverse=True,
        )

        best = items[0]
        current_callsign = None
        for d in items:
            current_callsign = _coalesce_text(current_callsign, d.get("current_callsign_from_cot"))
        current_callsign = _coalesce_text(current_callsign, best.get("observed_callsign"))

        selected = None
        if current_callsign:
            cur_key = str(current_callsign).strip().upper()
            for d in items:
                if str(d.get("observed_callsign") or "").strip().upper() == cur_key:
                    selected = d
                    break
        if selected is None:
            selected = best

        history: list[str] = []
        seen_history: set[str] = set()
        _add_unique(history, seen_history, current_callsign)
        for d in items:
            _add_unique(history, seen_history, d.get("observed_callsign"))

        last_cot_time = best.get("last_cot_time_dt")
        stale = best.get("stale_dt")
        is_current = bool(best.get("is_current"))

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

        endpoint_rows = []
        for d in items:
            endpoint_rows.append(
                {
                    "endpoint_id": d.get("endpoint_id"),
                    "callsign": d.get("observed_callsign"),
                    "endpoint_username": d.get("endpoint_username"),
                    "attribution_source": d.get("attribution_source"),
                    "last_event_time": d.get("last_event_time_dt").isoformat().replace("+00:00", "Z") if d.get("last_event_time_dt") else None,
                    "connection_event_type_id": d.get("connection_event_type_id"),
                    "connection_event_name": d.get("connection_event_name"),
                }
            )

        dev = {
            "endpoint_id": selected.get("endpoint_id"),
            "username": username,
            "client_uid": client_uid,
            "observed_callsign": current_callsign,
            "current_observed_callsign": current_callsign,
            "observed_callsigns": history,
            "previous_observed_callsigns": [x for x in history if str(x).strip().upper() != str(current_callsign or "").strip().upper()],
            "endpoint_username": selected.get("endpoint_username"),
            "attribution_source": selected.get("attribution_source"),
            "endpoint_rows": endpoint_rows,
            "last_cot_time": last_cot_time.isoformat().replace("+00:00", "Z") if last_cot_time else None,
            "stale": stale.isoformat().replace("+00:00", "Z") if stale else None,
            "is_current": is_current,
            "last_event_time": selected.get("last_event_time_dt").isoformat().replace("+00:00", "Z") if selected.get("last_event_time_dt") else None,
            "connection_event_type_id": selected.get("connection_event_type_id"),
            "connection_event_name": selected.get("connection_event_name"),
            "client_version": selected.get("client_version") or best.get("client_version"),
            "client_platform": selected.get("client_platform") or best.get("client_platform"),
            "client_product": selected.get("client_product") or best.get("client_product"),
            "tak_platform": selected.get("tak_platform") or best.get("tak_platform"),
            "tak_version": selected.get("tak_version") or best.get("tak_version"),
            "tak_device": selected.get("tak_device") or best.get("tak_device"),
            "tak_os": selected.get("tak_os") or best.get("tak_os"),
            "certs_n": max(int(d.get("certs_n") or 0) for d in items),
            "revoked_certs_n": max(int(d.get("revoked_certs_n") or 0) for d in items),
            "cot_seen": cot_seen,
            "seen_recently": seen_recently,
            "age_sec": age_sec,
            "age_human": age_human,
            "state": state,
        }

        out.setdefault(username, []).append(dev)

    for username, devices in out.items():
        devices.sort(
            key=lambda d: (
                1 if d.get("is_current") else 0,
                str(d.get("last_cot_time") or ""),
                str(d.get("last_event_time") or ""),
                str(d.get("client_uid") or ""),
            ),
            reverse=True,
        )

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
