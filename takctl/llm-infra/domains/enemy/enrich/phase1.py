from __future__ import annotations

import json
import math
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any


HOSTILE_TERMS = [
    "enemy",
    "fiend",
    "hostile",
    "armor",
    "armour",
    "infantry",
    "landstign",
    "landstigningsstyrka",
    "rysk",
    "ryska",
    "russian",
]


def _parse_json_stdin() -> dict[str, Any]:
    return json.load(sys.stdin)


def _find_query(data: dict[str, Any], name: str) -> dict[str, Any] | None:
    for q in data.get("queries", []) or []:
        if q.get("name") == name:
            return q
    return None


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    s = str(value).strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    if re.match(r".*[+-]\d{2}$", s):
        s = s + ":00"
    try:
        dt = datetime.fromisoformat(s)
    except Exception:
        try:
            dt = datetime.strptime(s, "%Y-%m-%d %H:%M")
            dt = dt.replace(tzinfo=timezone.utc)
        except Exception:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _tnr_from_dt(dt: datetime | None) -> str | None:
    if not dt:
        return None
    return dt.strftime("%d%H%MZ")


def _float_or_none(v: Any) -> float | None:
    try:
        if v is None or v == "":
            return None
        return float(v)
    except Exception:
        return None


def _decode_wkb_point_hex(hexstr: str | None) -> tuple[float | None, float | None]:
    if not hexstr:
        return (None, None)

    s = str(hexstr).strip()
    if s.startswith("0x") or s.startswith("0X"):
        s = s[2:]

    try:
        b = bytes.fromhex(s)
    except Exception:
        return (None, None)

    if len(b) < 21:
        return (None, None)

    byte_order = b[0]
    if byte_order not in (0, 1):
        return (None, None)

    endian = "little" if byte_order == 1 else "big"

    try:
        wkb_type = int.from_bytes(b[1:5], endian)
    except Exception:
        return (None, None)

    has_srid = bool(wkb_type & 0x20000000)
    geom_type = wkb_type & 0xFF

    if geom_type != 1:
        return (None, None)

    coord_off = 5
    if has_srid:
        if len(b) < 25:
            return (None, None)
        coord_off = 9

    try:
        import struct
        fmt = "<d" if byte_order == 1 else ">d"
        x = struct.unpack(fmt, b[coord_off:coord_off+8])[0]
        y = struct.unpack(fmt, b[coord_off+8:coord_off+16])[0]
    except Exception:
        return (None, None)

    return (x, y)

def _root_from_detail(detail_xml: str | None) -> ET.Element | None:
    if not detail_xml:
        return None
    try:
        return ET.fromstring(detail_xml)
    except Exception:
        return None


def _attr(root: ET.Element | None, tag: str, key: str) -> str:
    if root is None:
        return ""
    el = root.find(tag)
    if el is None:
        return ""
    return (el.attrib.get(key) or "").strip()


def _child_text(root: ET.Element | None, tag: str) -> str:
    if root is None:
        return ""
    el = root.find(tag)
    if el is None or el.text is None:
        return ""
    return el.text.strip()


def _remarks_text(root: ET.Element | None) -> str:
    return _child_text(root, "remarks")


def _extract_embedded_json(detail_xml: str | None, tag_name: str) -> dict[str, Any] | None:
    root = _root_from_detail(detail_xml)
    if root is None:
        return None
    el = root.find(tag_name)
    if el is None or not el.text:
        return None
    try:
        return json.loads(el.text)
    except Exception:
        return None


def _truncate(text: str, n: int = 180) -> str:
    s = " ".join((text or "").split())
    if len(s) <= n:
        return s
    return s[: n - 1].rstrip() + "…"


def _norm_text(s: str) -> str:
    return " ".join((s or "").strip().split()).lower()


def _hostile_score(text: str) -> int:
    t = _norm_text(text)
    score = 0
    for term in HOSTILE_TERMS:
        if term in t:
            score += 1
    return score


def _round_coord(v: float | None, digits: int = 3) -> float | None:
    if v is None:
        return None
    return round(v, digits)


def _cluster_key(s: dict[str, Any]) -> str:
    lat = s.get("lat")
    lon = s.get("lon")
    excerpt = _norm_text(s.get("excerpt") or s.get("remarks") or "")
    if lat is not None and lon is not None:
        latk = round(float(lat), 2)
        lonk = round(float(lon), 2)
    else:
        latk = None
        lonk = None

    label = "generic"
    if "armor" in excerpt or "armour" in excerpt:
        label = "armor"
    elif "infantry" in excerpt:
        label = "infantry"
    elif "landstign" in excerpt:
        label = "landing"
    elif "enemy" in excerpt or "fiend" in excerpt or "hostile" in excerpt or "rysk" in excerpt or "russian" in excerpt:
        label = "hostile"

    if latk is not None and lonk is not None:
        return f"{label}:{latk:.2f}:{lonk:.2f}"
    return f"{label}:noloc:{excerpt[:48]}"


def _sort_sightings_desc(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        items,
        key=lambda x: (
            _parse_dt(x.get("time_utc")) or datetime.min.replace(tzinfo=timezone.utc),
            x.get("hostile_score", 0),
        ),
        reverse=True,
    )


def _build_chat_sightings(chat_rows: list[list[Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in chat_rows:
        ts_utc, chat_room, sender_callsign, chat_content = (list(row) + [None, None, None, None])[:4]
        dt = _parse_dt(ts_utc)
        excerpt = " ".join(str(chat_content or "").split()).strip()
        s = {
            "source": "chat",
            "reporter": sender_callsign or "",
            "reporter_callsign": sender_callsign or "",
            "room": chat_room or "",
            "raw_basis": "chat_content",
            "excerpt": excerpt,
            "hostile_score": max(1, _hostile_score(excerpt)),
            "time_utc": dt.isoformat().replace("+00:00", "Z") if dt else (ts_utc or ""),
            "time_tnr": _tnr_from_dt(dt),
        }
        out.append(s)
    return out


def _build_cot_sightings(cot_rows: list[list[Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in cot_rows:
        uid, cot_type, how, time_utc, stale_utc, point_wkb_hex, detail_xml = (list(row) + [None] * 7)[:7]

        dt = _parse_dt(time_utc)
        stale_dt = _parse_dt(stale_utc)
        lat, lon = _decode_wkb_point_hex(point_wkb_hex)

        root = _root_from_detail(detail_xml)
        remarks = _remarks_text(root)
        contact_callsign = _attr(root, "contact", "callsign")
        creator_callsign = _attr(root, "creator", "callsign")
        creator_uid = _attr(root, "creator", "uid")

        embedded = _extract_embedded_json(detail_xml, "taks_chat") or _extract_embedded_json(detail_xml, "taks_report") or {}
        confidence = embedded.get("confidence")
        description = embedded.get("description") or embedded.get("intent") or ""

        excerpt_source = remarks or description or contact_callsign or str(uid or "")
        excerpt = _truncate(excerpt_source, 180)

        hostile_basis = " ".join(
            x for x in [
                remarks,
                description,
                contact_callsign,
                str(cot_type or ""),
            ] if x
        )
        score = _hostile_score(hostile_basis)
        if str(cot_type or "").startswith("a-h-"):
            score += 2
        elif "enemy_ground_contact" in json.dumps(embedded, ensure_ascii=False):
            score += 2
        elif score > 0:
            score = max(score, 1)

        s = {
            "source": "cot",
            "reporter": uid or "",
            "reporter_callsign": contact_callsign or creator_callsign or uid or "",
            "track_callsign": contact_callsign or "",
            "creator_callsign": creator_callsign or "",
            "creator_uid": creator_uid or "",
            "cot_type": cot_type or "",
            "how": how or "",
            "raw_basis": "detail_xml",
            "remarks": remarks,
            "excerpt": excerpt,
            "hostile_score": score,
            "time_utc": dt.isoformat().replace("+00:00", "Z") if dt else (time_utc or ""),
            "time_tnr": _tnr_from_dt(dt),
            "stale_utc": stale_dt.isoformat().replace("+00:00", "Z") if stale_dt else (stale_utc or ""),
            "stale_tnr": _tnr_from_dt(stale_dt),
            "lat": lat,
            "lon": lon,
        }

        if confidence is not None:
            s["confidence"] = confidence

        if embedded.get("type"):
            s["contact_type"] = embedded.get("type")

        if embedded.get("location"):
            eloc = embedded.get("location") or {}
            if s["lat"] is None and _float_or_none(eloc.get("lat")) is not None:
                s["lat"] = _float_or_none(eloc.get("lat"))
            if s["lon"] is None and _float_or_none(eloc.get("lon")) is not None:
                s["lon"] = _float_or_none(eloc.get("lon"))

        out.append(s)
    return out


def _dedupe_sightings(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[Any, ...]] = set()
    out: list[dict[str, Any]] = []
    for s in items:
        key = (
            s.get("source"),
            s.get("reporter"),
            s.get("reporter_callsign"),
            s.get("time_utc"),
            s.get("excerpt"),
            _round_coord(s.get("lat"), 4),
            _round_coord(s.get("lon"), 4),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out


def _cluster_sightings(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for s in items:
        groups[_cluster_key(s)].append(s)

    clusters: list[dict[str, Any]] = []
    for _, group in groups.items():
        ordered = _sort_sightings_desc(group)
        latest = ordered[0]
        reporters: list[str] = []
        for s in ordered:
            rc = str(s.get("reporter_callsign") or s.get("reporter") or "").strip()
            if rc and rc not in reporters:
                reporters.append(rc)

        examples: list[str] = []
        for s in ordered:
            ex = str(s.get("excerpt") or s.get("remarks") or "").strip()
            if ex and ex not in examples:
                examples.append(ex)
            if len(examples) >= 3:
                break

        source_counts: dict[str, int] = {}
        for s in group:
            src = str(s.get("source") or "unknown")
            source_counts[src] = source_counts.get(src, 0) + 1

        lat_values = [float(s["lat"]) for s in group if s.get("lat") is not None]
        lon_values = [float(s["lon"]) for s in group if s.get("lon") is not None]

        cluster: dict[str, Any] = {
            "latest_time_tnr": latest.get("time_tnr"),
            "latest_time_utc": latest.get("time_utc"),
            "observations": len(group),
            "reporters": reporters,
            "sources": source_counts,
            "examples": examples,
        }

        if lat_values and lon_values:
            cluster["position"] = {
                "lat": round(sum(lat_values) / len(lat_values), 3),
                "lon": round(sum(lon_values) / len(lon_values), 3),
            }

        clusters.append(cluster)

    clusters.sort(
        key=lambda c: _parse_dt(c.get("latest_time_utc")) or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    return clusters


def enrich(data: dict[str, Any]) -> dict[str, Any]:
    chat_q = _find_query(data, "010_enemy_chatter_hits") or {}
    cot_q = _find_query(data, "020_enemy_latestcot_candidates") or {}

    chat_rows = chat_q.get("rows") or []
    cot_rows = cot_q.get("rows") or []

    sightings = []
    sightings.extend(_build_chat_sightings(chat_rows))
    sightings.extend(_build_cot_sightings(cot_rows))
    sightings = _dedupe_sightings(sightings)
    sightings = _sort_sightings_desc(sightings)

    clusters = _cluster_sightings(sightings)

    return {
        "domain": "enemy",
        "enemy": {
            "clusters": clusters,
            "counts": {
                "chat_sightings": sum(1 for s in sightings if s.get("source") == "chat"),
                "cot_sightings": sum(1 for s in sightings if s.get("source") == "cot"),
                "total_sightings": len(sightings),
            },
            "sightings": sightings,
        },
        "generated_utc": data.get("generated_utc"),
        "ok": True,
        "phase": "phase1",
        "queries": data.get("queries", []),
    }


def main() -> int:
    out = enrich(_parse_json_stdin())
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
