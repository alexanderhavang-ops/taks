from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Tuple

from takctl.onboarding import fal


def _s(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _upper(v: Any) -> str:
    return _s(v).upper()


def _sorted_counts(d: Dict[str, int]) -> Dict[str, int]:
    return dict(sorted(d.items(), key=lambda kv: (-kv[1], kv[0])))


def _query_rows(evidence: Dict[str, Any], name: str) -> List[List[Any]]:
    for q in evidence.get("queries") or []:
        if _s(q.get("name")) == name:
            rows = q.get("rows") or []
            return rows if isinstance(rows, list) else []
    return []


def _parse_detail_xml(detail_xml: str) -> Dict[str, str]:
    out = {"callsign": "", "role": "", "remarks": ""}
    s = _s(detail_xml)
    if not s:
        return out
    try:
        root = ET.fromstring(s)
    except Exception:
        return out

    contact = root.find("contact")
    if contact is not None:
        out["callsign"] = _s(contact.attrib.get("callsign"))

    group = root.find("__group")
    if group is not None:
        out["role"] = _s(group.attrib.get("role"))

    remarks = root.find("remarks")
    if remarks is not None and remarks.text:
        out["remarks"] = _s(remarks.text)

    return out


def _wkb_point_hex_to_latlon(hex_wkb: str) -> Optional[Tuple[float, float]]:
    s = _s(hex_wkb)
    if not s:
        return None
    try:
        b = bytes.fromhex(s)
    except Exception:
        return None
    if len(b) < 1 + 4 + 16:
        return None

    endian = b[0]
    little = endian == 1
    bo = "little" if little else "big"

    geom_type = int.from_bytes(b[1:5], bo, signed=False)
    pos = 5

    has_srid = bool(geom_type & 0x20000000)
    base_type = geom_type & 0xFF

    if has_srid:
        if len(b) < pos + 4:
            return None
        pos += 4

    if base_type != 1:
        return None
    if len(b) < pos + 16:
        return None

    import struct
    fmt = "<dd" if little else ">dd"
    x, y = struct.unpack(fmt, b[pos:pos + 16])
    return (float(y), float(x))  # lat, lon


def _tnr_from_iso(ts: str) -> str:
    # Accept both:
    #  - 2026-03-12T17:14:44+00:00
    #  - 2026-03-12 17:14:44+00:00   (str(datetime))
    s = _s(ts)
    if len(s) < 16:
        return ""
    if s[4] != "-" or s[7] != "-" or s[13] != ":":
        return ""
    if s[10] not in ("T", " "):
        return ""
    dd = s[8:10]
    hh = s[11:13]
    mm = s[14:16]
    if not (dd.isdigit() and hh.isdigit() and mm.isdigit()):
        return ""
    return f"{dd}{hh}{mm}Z"


def _fal_parse_callsign(cs: str) -> Optional[Dict[str, Any]]:
    """
    Use fal.py as the single authority for doctrinal parsing.
    policy_cfg is optional; for presence we pass None (no hvbat mapping needed).
    """
    callsign = _upper(cs)
    if not callsign:
        return None
    try:
        out = fal.parse_callsign(None, callsign)
    except Exception:
        return None
    return out if isinstance(out, dict) and out else None


def _unit_key_from_fal(parsed: Dict[str, Any]) -> str:
    """
    Conservative: group by the most specific callsign-like key fal provides.
    No guessing.
    """
    for k in (
        "group_callsign",
        "platoon_callsign",
        "company_callsign",
        "battalion_callsign",
        "callsign",
    ):
        v = _upper(parsed.get(k))
        if v:
            return v
    return ""


def _group_non_doctrinal(rows: List[Dict[str, Any]], threshold_deg: float = 0.01) -> List[Dict[str, Any]]:
    # coarse spatial clustering to avoid dumping individual spam
    clusters: List[Dict[str, Any]] = []
    for r in rows:
        lat = r.get("lat")
        lon = r.get("lon")
        assigned = None

        if lat is not None and lon is not None:
            for c in clusters:
                if c.get("lat") is None or c.get("lon") is None:
                    continue
                if abs(float(lat) - float(c["lat"])) <= threshold_deg and abs(float(lon) - float(c["lon"])) <= threshold_deg:
                    assigned = c
                    break
        else:
            for c in clusters:
                if c.get("lat") is None and c.get("lon") is None:
                    assigned = c
                    break

        if assigned is None:
            assigned = {"rows": [], "lat": lat, "lon": lon}
            clusters.append(assigned)
        assigned["rows"].append(r)

    out: List[Dict[str, Any]] = []
    for c in clusters:
        rws = c["rows"]
        callsigns: List[str] = []
        roles: Dict[str, int] = {}
        latest = ""

        for r in rws:
            cs = _s(r.get("callsign"))
            if cs and cs not in callsigns:
                callsigns.append(cs)
            role = _s(r.get("role"))
            if role:
                roles[role] = roles.get(role, 0) + 1
            lt = _s(r.get("time_tnr"))
            if lt and (not latest or lt > latest):
                latest = lt

        item: Dict[str, Any] = {
            "observations": len(rws),
            "latest_time": latest,
            "callsigns": callsigns,
        }
        if c.get("lat") is not None and c.get("lon") is not None:
            item["position"] = {"lat": float(c["lat"]), "lon": float(c["lon"])}
        if roles:
            item["roles"] = _sorted_counts(roles)

        out.append(item)

    out.sort(key=lambda x: (-int(x["observations"]), x.get("latest_time", ""), ",".join(x.get("callsigns", []))))
    return out


def enrich(evidence: Dict[str, Any]) -> Dict[str, Any]:
    latest_rows = _query_rows(evidence, "010_presence_latest_friendlies")
    meta_rows = _query_rows(evidence, "020_presence_latest_metadata")

    parsed_rows: List[Dict[str, Any]] = []

    for row in latest_rows:
        if not isinstance(row, list) or len(row) < 7:
            continue
        time_utc, stale_utc, uid, cot_type, how, event_pt, detail_xml = row[:7]

        detail = _parse_detail_xml(detail_xml)
        callsign = _s(detail.get("callsign"))
        role = _s(detail.get("role"))

        latlon = _wkb_point_hex_to_latlon(_s(event_pt))
        time_tnr = _tnr_from_iso(_s(time_utc))
        stale_tnr = _tnr_from_iso(_s(stale_utc))

        fal_parsed = _fal_parse_callsign(callsign)
        doctrinal = bool(fal_parsed)
        unit = _unit_key_from_fal(fal_parsed) if fal_parsed else ""

        rec: Dict[str, Any] = {
            "callsign": callsign,
            "role": role,
            "time_tnr": time_tnr,
            "stale_tnr": stale_tnr,
            "doctrinal": doctrinal,
            "unit": unit,
        }
        if latlon is not None:
            rec["lat"], rec["lon"] = latlon[0], latlon[1]
        parsed_rows.append(rec)

    # doctrinal vs non-doctrinal split
    doctrinal_rows = [r for r in parsed_rows if r.get("doctrinal") and _s(r.get("unit"))]
    non_doctrinal_rows = [r for r in parsed_rows if not r.get("doctrinal")]

    # doctrinal aggregation by unit key
    by_unit: Dict[str, Dict[str, Any]] = {}
    for r in doctrinal_rows:
        unit = _s(r.get("unit"))
        slot = by_unit.setdefault(
            unit,
            {"unit": unit, "observations": 0, "latest_time": "", "roles": {}, "positions": []},
        )
        slot["observations"] += 1

        lt = _s(r.get("time_tnr"))
        if lt and (not slot["latest_time"] or lt > slot["latest_time"]):
            slot["latest_time"] = lt

        role = _s(r.get("role"))
        if role:
            slot["roles"][role] = slot["roles"].get(role, 0) + 1

        lat = r.get("lat")
        lon = r.get("lon")
        if lat is not None and lon is not None:
            slot["positions"].append({"lat": float(lat), "lon": float(lon)})

    doctrinal_units: List[Dict[str, Any]] = []
    for _, item in by_unit.items():
        item["roles"] = _sorted_counts(item["roles"])
        doctrinal_units.append(item)
    doctrinal_units.sort(key=lambda x: (-int(x["observations"]), x["unit"]))

    # non-doctrinal clustering
    nd_clusters = _group_non_doctrinal(non_doctrinal_rows)
    largest = nd_clusters[0] if nd_clusters else None
    others = nd_clusters[1:4] if len(nd_clusters) > 1 else []

    # picture_time from metadata
    picture_time = ""
    if meta_rows and isinstance(meta_rows[0], list) and len(meta_rows[0]) >= 1:
        picture_time = _tnr_from_iso(_s(meta_rows[0][0]))

    # stale_time = max stale_tnr across rows
    stale_time = ""
    for r in parsed_rows:
        st = _s(r.get("stale_tnr"))
        if st and (not stale_time or st > stale_time):
            stale_time = st

    # quick visibility/debug: which callsigns were considered doctrinal?
    doctrinal_callsigns = sorted({_upper(r.get("callsign")) for r in doctrinal_rows if _s(r.get("callsign"))})

    return {
        "picture_time": picture_time,
        "stale_time": stale_time,
        "doctrinal_units": doctrinal_units,
        "doctrinal_callsigns": doctrinal_callsigns,
        "largest_non_doctrinal_cluster": largest,
        "other_non_doctrinal_contacts": others,
    }
