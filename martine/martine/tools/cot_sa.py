from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

import psycopg2

from takctl.config import load_config, load_secrets
from takctl.onboarding.fal import derive_fal_ctx


# ------------------------------------------------------------
# DB helpers
# ------------------------------------------------------------

def _db_conn():
    cfg = load_config()
    sec = load_secrets()

    return psycopg2.connect(
        dbname=str(cfg.get("db_name", "cot")),
        host=str(cfg.get("db_host", "127.0.0.1")),
        port=int(cfg.get("db_port", "5432")),
        user=str(cfg.get("db_user", "tak")),
        password=str(sec.get("db_password", "")),
    )


def _query_all(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    conn = _db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            cols = [d.name for d in cur.description]
            rows = cur.fetchall()
        return [dict(zip(cols, row)) for row in rows]
    finally:
        conn.close()


def _query_one(sql: str, params: tuple[Any, ...] = ()) -> Optional[dict[str, Any]]:
    rows = _query_all(sql, params)
    return rows[0] if rows else None


# ------------------------------------------------------------
# Basic geo helpers
# ------------------------------------------------------------

EARTH_R_M = 6371000.0


def _deg2rad(v: float) -> float:
    return v * math.pi / 180.0


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1 = _deg2rad(lat1)
    p2 = _deg2rad(lat2)
    dp = _deg2rad(lat2 - lat1)
    dl = _deg2rad(lon2 - lon1)

    a = math.sin(dp / 2.0) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return EARTH_R_M * c


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> int:
    p1 = _deg2rad(lat1)
    p2 = _deg2rad(lat2)
    dl = _deg2rad(lon2 - lon1)

    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    brng = math.degrees(math.atan2(y, x))
    return int((brng + 360.0) % 360.0)


# ------------------------------------------------------------
# Very small MGRS placeholder
# Replace with real MGRS conversion when ready.
# ------------------------------------------------------------

def to_mgrs(lat: float, lon: float) -> str:
    return f"LATLON {lat:.5f},{lon:.5f}"


# ------------------------------------------------------------
# Time helpers
# ------------------------------------------------------------

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | None) -> str:
    if dt is None:
        return ""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _age_sec(dt: datetime | None) -> Optional[int]:
    if dt is None:
        return None
    return max(0, int((_now_utc() - dt.astimezone(timezone.utc)).total_seconds()))


# ------------------------------------------------------------
# Identity / latest position lookup
# ------------------------------------------------------------

@dataclass(frozen=True)
class Contact:
    callsign: str
    uid: str
    cot_type: str
    how: str
    servertime: datetime
    lat: float
    lon: float
    hae: float


def _latest_contact_by_uid(uid: str) -> Optional[Contact]:
    row = _query_one(
        """
        SELECT
          uid,
          COALESCE(
            NULLIF(
              substring(detail from 'callsign="([^"]+)"'),
              ''
            ),
            uid
          ) AS callsign,
          cot_type,
          how,
          servertime,
          ST_Y(event_pt::geometry) AS lat,
          ST_X(event_pt::geometry) AS lon,
          COALESCE(point_hae, 0) AS hae
        FROM cot_router
        WHERE uid = %s
          AND event_pt IS NOT NULL
        ORDER BY servertime DESC
        LIMIT 1
        """,
        (uid,),
    )
    if not row:
        return None
    return Contact(
        callsign=str(row["callsign"] or row["uid"] or "").strip(),
        uid=str(row["uid"] or "").strip(),
        cot_type=str(row["cot_type"] or "").strip(),
        how=str(row["how"] or "").strip(),
        servertime=row["servertime"],
        lat=float(row["lat"]),
        lon=float(row["lon"]),
        hae=float(row["hae"] or 0.0),
    )


def _latest_contact_by_callsign(callsign: str) -> Optional[Contact]:
    row = _query_one(
        """
        SELECT *
        FROM (
          SELECT
            uid,
            COALESCE(
              NULLIF(
                substring(detail from 'callsign="([^"]+)"'),
                ''
              ),
              uid
            ) AS callsign,
            cot_type,
            how,
            servertime,
            ST_Y(event_pt::geometry) AS lat,
            ST_X(event_pt::geometry) AS lon,
            COALESCE(point_hae, 0) AS hae
          FROM cot_router
          WHERE event_pt IS NOT NULL
        ) q
        WHERE lower(callsign) = lower(%s)
        ORDER BY servertime DESC
        LIMIT 1
        """,
        (callsign,),
    )
    if not row:
        return None
    return Contact(
        callsign=str(row["callsign"] or row["uid"] or "").strip(),
        uid=str(row["uid"] or "").strip(),
        cot_type=str(row["cot_type"] or "").strip(),
        how=str(row["how"] or "").strip(),
        servertime=row["servertime"],
        lat=float(row["lat"]),
        lon=float(row["lon"]),
        hae=float(row["hae"] or 0.0),
    )


def _sender_company_suffix(sender_callsign: str) -> str:
    s = (sender_callsign or "").strip().upper()
    # good enough first pass:
    # EAQQ1 -> QQ
    # ATQQ1 -> QQ
    # QQ1   -> QQ
    if not s:
        return ""
    core = s.rstrip("0123456789")
    if len(core) >= 2 and core[-2:].isalpha():
        return core[-2:]
    return ""


def _contextual_callsign_candidates(raw: str, sender_callsign: str) -> list[str]:
    q = (raw or "").strip().upper()
    if not q:
        return []

    out: list[str] = [q]
    suffix = _sender_company_suffix(sender_callsign)
    if not suffix:
        return out

    import re

    # Only expand shortforms that do NOT already contain the company suffix.
    # EA1 -> EAQQ1
    # AT1 -> ATQQ1
    # QQ1 stays QQ1
    m = re.fullmatch(r"([A-Z]{2,3})(\d+)", q)
    if m:
        prefix, num = m.groups()
        if not prefix.endswith(suffix):
            out.append(f"{prefix}{suffix}{num}")

    # EA -> EAQQ
    # QQ stays QQ
    m2 = re.fullmatch(r"([A-Z]{2,3})", q)
    if m2:
        if not q.endswith(suffix):
            out.append(f"{q}{suffix}")

    seen = set()
    uniq = []
    for x in out:
        if x not in seen:
            seen.add(x)
            uniq.append(x)
    return uniq


def _resolve_contact_contextual(callsign_or_uid: str, sender_callsign: str = "") -> Optional[Contact]:
    x = (callsign_or_uid or "").strip()
    if not x:
        return None

    # exact first
    c = _latest_contact_by_uid(x)
    if c:
        return c
    c = _latest_contact_by_callsign(x)
    if c:
        return c

    # contextual FAL-ish candidates next
    for cand in _contextual_callsign_candidates(x, sender_callsign):
        c = _latest_contact_by_callsign(cand)
        if c:
            return c

    return None


def _resolve_contact(callsign_or_uid: str) -> Optional[Contact]:
    x = (callsign_or_uid or "").strip()
    if not x:
        return None
    c = _latest_contact_by_uid(x)
    if c:
        return c
    return _latest_contact_by_callsign(x)


def resolve_sender_contact(sender_uid: str = "", sender_callsign: str = "") -> Optional[Contact]:
    c = _resolve_contact(sender_uid)
    if c:
        return c
    return _resolve_contact(sender_callsign)


# ------------------------------------------------------------
# Tool functions: phase 1
# ------------------------------------------------------------

def get_current_time() -> dict[str, Any]:
    now = _now_utc()
    return {
        "ok": True,
        "utc_time": _iso(now),
        "local_time": now.astimezone().isoformat(timespec="seconds"),
        "timezone": str(now.astimezone().tzinfo or "local"),
    }


def get_my_position(*, sender_uid: str = "", sender_callsign: str = "") -> dict[str, Any]:
    c = resolve_sender_contact(sender_uid=sender_uid, sender_callsign=sender_callsign)
    if not c:
        return {
            "ok": False,
            "error": "could not resolve sender position",
            "sender_uid": sender_uid,
            "sender_callsign": sender_callsign,
        }

    return {
        "ok": True,
        "callsign": c.callsign,
        "uid": c.uid,
        "last_seen": _iso(c.servertime),
        "lat": c.lat,
        "lon": c.lon,
        "hae": c.hae,
        "mgrs": to_mgrs(c.lat, c.lon),
        "age_sec": _age_sec(c.servertime),
    }


def get_my_mgrs(*, sender_uid: str = "", sender_callsign: str = "") -> dict[str, Any]:
    c = resolve_sender_contact(sender_uid=sender_uid, sender_callsign=sender_callsign)
    if not c:
        return {
            "ok": False,
            "error": "could not resolve sender position",
            "sender_uid": sender_uid,
            "sender_callsign": sender_callsign,
        }

    return {
        "ok": True,
        "callsign": c.callsign,
        "uid": c.uid,
        "mgrs": to_mgrs(c.lat, c.lon),
        "last_seen": _iso(c.servertime),
        "age_sec": _age_sec(c.servertime),
    }


def get_contact_status(*, callsign_or_uid: str, sender_callsign: str = "") -> dict[str, Any]:
    c = _resolve_contact_contextual(callsign_or_uid, sender_callsign=sender_callsign)
    if not c:
        return {
            "ok": False,
            "error": "contact not found",
            "query": callsign_or_uid,
        }

    return {
        "ok": True,
        "callsign": c.callsign,
        "uid": c.uid,
        "last_seen": _iso(c.servertime),
        "lat": c.lat,
        "lon": c.lon,
        "hae": c.hae,
        "mgrs": to_mgrs(c.lat, c.lon),
        "cot_type": c.cot_type,
        "how": c.how,
        "age_sec": _age_sec(c.servertime),
    }


def get_last_seen(*, callsign_or_uid: str, sender_callsign: str = "") -> dict[str, Any]:
    c = _resolve_contact_contextual(callsign_or_uid, sender_callsign=sender_callsign)
    if not c:
        return {
            "ok": False,
            "error": "contact not found",
            "query": callsign_or_uid,
        }

    return {
        "ok": True,
        "callsign": c.callsign,
        "uid": c.uid,
        "last_seen": _iso(c.servertime),
        "age_sec": _age_sec(c.servertime),
        "cot_type": c.cot_type,
    }


def get_distance_to_callsign(
    *,
    target_callsign_or_uid: str,
    sender_uid: str = "",
    sender_callsign: str = "",
) -> dict[str, Any]:
    me = resolve_sender_contact(sender_uid=sender_uid, sender_callsign=sender_callsign)
    target = _resolve_contact_contextual(target_callsign_or_uid, sender_callsign=me.callsign if me else sender_callsign)

    if not me:
        return {
            "ok": False,
            "error": "could not resolve sender position",
            "sender_uid": sender_uid,
            "sender_callsign": sender_callsign,
        }
    if not target:
        return {
            "ok": False,
            "error": "target not found",
            "query": target_callsign_or_uid,
        }

    return {
        "ok": True,
        "from": {
            "callsign": me.callsign,
            "uid": me.uid,
            "mgrs": to_mgrs(me.lat, me.lon),
            "age_sec": _age_sec(me.servertime),
        },
        "to": {
            "callsign": target.callsign,
            "uid": target.uid,
            "mgrs": to_mgrs(target.lat, target.lon),
            "age_sec": _age_sec(target.servertime),
        },
        "distance_m": int(round(distance_m(me.lat, me.lon, target.lat, target.lon))),
        "bearing_deg": bearing_deg(me.lat, me.lon, target.lat, target.lon),
    }


def get_nearest_friendly(
    *,
    sender_uid: str = "",
    sender_callsign: str = "",
    limit: int = 20,
) -> dict[str, Any]:
    me = resolve_sender_contact(sender_uid=sender_uid, sender_callsign=sender_callsign)
    if not me:
        return {
            "ok": False,
            "error": "could not resolve sender position",
            "sender_uid": sender_uid,
            "sender_callsign": sender_callsign,
        }

    rows = _query_all(
        """
        SELECT *
        FROM (
          SELECT
            uid,
            COALESCE(
              NULLIF(
                substring(detail from 'callsign="([^"]+)"'),
                ''
              ),
              uid
            ) AS callsign,
            cot_type,
            how,
            servertime,
            ST_Y(event_pt::geometry) AS lat,
            ST_X(event_pt::geometry) AS lon,
            COALESCE(point_hae, 0) AS hae
          FROM cot_router
          WHERE event_pt IS NOT NULL
        ) q
        WHERE uid <> %s
          AND cot_type LIKE 'a-f%%'
        ORDER BY servertime DESC
        LIMIT %s
        """,
        (me.uid, limit),
    )

    best: Optional[dict[str, Any]] = None
    for row in rows:
        d = distance_m(me.lat, me.lon, float(row["lat"]), float(row["lon"]))
        if best is None or d < best["distance_m"]:
            best = {
                "callsign": str(row["callsign"] or row["uid"] or "").strip(),
                "uid": str(row["uid"] or "").strip(),
                "last_seen": _iso(row["servertime"]),
                "mgrs": to_mgrs(float(row["lat"]), float(row["lon"])),
                "distance_m": int(round(d)),
                "bearing_deg": bearing_deg(me.lat, me.lon, float(row["lat"]), float(row["lon"])),
                "age_sec": _age_sec(row["servertime"]),
            }

    if best is None:
        return {
            "ok": False,
            "error": "no friendly contacts found",
        }

    return {
        "ok": True,
        "reference": {
            "callsign": me.callsign,
            "uid": me.uid,
            "mgrs": to_mgrs(me.lat, me.lon),
        },
        "nearest": best,
    }


def get_enemy_contacts_near_me(
    *,
    sender_uid: str = "",
    sender_callsign: str = "",
    radius_m: int = 2000,
    minutes: int = 60,
    limit: int = 20,
) -> dict[str, Any]:
    me = resolve_sender_contact(sender_uid=sender_uid, sender_callsign=sender_callsign)
    if not me:
        return {
            "ok": False,
            "error": "could not resolve sender position",
            "sender_uid": sender_uid,
            "sender_callsign": sender_callsign,
        }

    rows = _query_all(
        """
        SELECT *
        FROM (
          SELECT
            uid,
            COALESCE(
              NULLIF(
                substring(detail from 'callsign="([^"]+)"'),
                ''
              ),
              uid
            ) AS callsign,
            cot_type,
            how,
            servertime,
            ST_Y(event_pt::geometry) AS lat,
            ST_X(event_pt::geometry) AS lon
          FROM cot_router
          WHERE event_pt IS NOT NULL
            AND servertime >= (now() - (%s || ' minutes')::interval)
        ) q
        WHERE cot_type LIKE 'a-h%%'
        ORDER BY servertime DESC
        LIMIT %s
        """,
        (str(minutes), limit),
    )

    items = []
    for row in rows:
        lat = float(row["lat"])
        lon = float(row["lon"])
        d = distance_m(me.lat, me.lon, lat, lon)
        if d > float(radius_m):
            continue
        items.append(
            {
                "callsign": str(row["callsign"] or row["uid"] or "").strip(),
                "uid": str(row["uid"] or "").strip(),
                "distance_m": int(round(d)),
                "bearing_deg": bearing_deg(me.lat, me.lon, lat, lon),
                "last_seen": _iso(row["servertime"]),
                "age_sec": _age_sec(row["servertime"]),
                "source": "cot",
                "cot_type": str(row["cot_type"] or "").strip(),
            }
        )

    return {
        "ok": True,
        "reference": {
            "callsign": me.callsign,
            "uid": me.uid,
            "mgrs": to_mgrs(me.lat, me.lon),
        },
        "query": {
            "radius_m": radius_m,
            "minutes": minutes,
        },
        "count": len(items),
        "items": items,
    }
