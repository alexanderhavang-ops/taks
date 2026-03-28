#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

AGENT_RUNTIME_JSON = Path("/opt/tak/replay/state/agent_runtime.json")
from xml.sax.saxutils import escape

HERE = Path(__file__).resolve().parent
REPO_ROOT = Path("/opt/tak/tools/takctl")
sys.path.insert(0, str(REPO_ROOT / "takctl"))

try:
    from takctl.onboarding.fal import parse_callsign  # type: ignore
except Exception:
    parse_callsign = None


@dataclass
class Segment:
    t0: float
    t1: float
    p0: Tuple[float, float]
    p1: Tuple[float, float]
    activity: str


def iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def lerp(a: float, b: float, r: float) -> float:
    return a + (b - a) * r


def heading_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    y = math.sin(math.radians(lon2 - lon1)) * math.cos(math.radians(lat2))
    x = (
        math.cos(math.radians(lat1)) * math.sin(math.radians(lat2))
        - math.sin(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.cos(math.radians(lon2 - lon1))
    )
    brng = math.degrees(math.atan2(y, x))
    return (brng + 360.0) % 360.0


def meters_to_latlon_offset(lat: float, east_m: float, north_m: float) -> Tuple[float, float]:
    dlat = north_m / 111_320.0
    dlon = east_m / (111_320.0 * max(0.1, math.cos(math.radians(lat))))
    return dlat, dlon


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def entity_uid(scenario_id: str, callsign: str) -> str:
    return f"replay:{scenario_id}:{callsign}"


def auto_inherit(callsign: str) -> Optional[str]:
    i = len(callsign)
    while i > 0 and callsign[i - 1].isdigit():
        i -= 1
    if i < len(callsign):
        base = callsign[:i]
        return base or None
    return None


def trailing_number(callsign: str) -> Optional[int]:
    i = len(callsign)
    while i > 0 and callsign[i - 1].isdigit():
        i -= 1
    if i == len(callsign):
        return None
    try:
        return int(callsign[i:])
    except Exception:
        return None


def classify_blue(callsign: str) -> Dict[str, Any]:
    if parse_callsign is None:
        return {}
    try:
        return parse_callsign(None, callsign)
    except Exception:
        return {}


def default_cot_type(ent: Dict[str, Any]) -> str:
    side = str(ent.get("side", "blue"))
    if side != "blue":
        return "a-h-S"
    fal = ent.get("_fal") or {}
    if fal.get("is_individual"):
        return "a-f-G-U-C-I"
    return "a-f-G-U-C"


def role_grouping(ent: Dict[str, Any]) -> Tuple[str, str]:
    side = str(ent.get("side", "blue"))
    role = str(ent.get("role", "unit"))
    fal = ent.get("_fal") or {}

    if side == "red":
        return ("Red", "Team Member")

    if role in ("battalion", "hq", "command_post", "company"):
        return ("Cyan", "HQ")

    if fal.get("is_individual"):
        hint = str(fal.get("role_hint") or "")
        if hint == "leader":
            return ("Cyan", "Team Lead")
        if hint == "deputy":
            return ("Cyan", "Assistant Team Lead")
        return ("Cyan", "Team Member")

    level = str(fal.get("role_level") or "")
    if level in ("company", "battalion_or_other"):
        return ("Cyan", "HQ")
    return ("Cyan", "Team Member")


def droid_value(uid: str, callsign: str, ent: Dict[str, Any]) -> str:
    return str(ent.get("droid") or callsign or uid)


def formation_offset_from_suffix(callsign: str, spacing_m: float = 8.0) -> Tuple[float, float]:
    n = trailing_number(callsign)
    if n is None or n <= 0:
        return (0.0, 0.0)
    if n == 1:
        return (0.0, 0.0)
    idx = n - 2
    row = idx // 2 + 1
    side = -1 if idx % 2 == 0 else 1
    east_m = side * row * spacing_m
    north_m = -row * spacing_m * 0.8
    return (east_m, north_m)


def rotate_offset(east_m: float, north_m: float, heading_deg_value: float) -> Tuple[float, float]:
    rad = math.radians(heading_deg_value)
    re = east_m * math.cos(rad) - north_m * math.sin(rad)
    rn = east_m * math.sin(rad) + north_m * math.cos(rad)
    return re, rn


def build_cot(
    *,
    uid: str,
    cot_type: str,
    callsign: str,
    lat: float,
    lon: float,
    activity: str,
    now_dt: datetime,
    stale_seconds: int,
    speed_mps: float,
    heading: float,
    role: str,
    side: str,
    ent: Dict[str, Any],
) -> str:
    time_s = iso_z(now_dt)
    stale_s = iso_z(now_dt + timedelta(seconds=stale_seconds))
    group_name, group_role = role_grouping(ent)
    droid = droid_value(uid, callsign, ent)

    detail_extras = [
        f'<contact callsign="{escape(callsign)}" endpoint="*:-1:stcp"/>',
        f'<__group name="{escape(group_name)}" role="{escape(group_role)}"/>',
        f'<track speed="{speed_mps:.2f}" course="{heading:.1f}"/>',
        f'<uid Droid="{escape(droid)}"/>',
        f'<remarks>{escape(activity)}</remarks>',
    ]
    if side == "blue":
        detail_extras.append('<archive/>')

    detail = "".join(detail_extras)
    return (
        f'<event version="2.0" uid="{escape(uid)}" type="{escape(cot_type)}" how="m-g" '
        f'time="{time_s}" start="{time_s}" stale="{stale_s}">'
        f'<point lat="{lat:.6f}" lon="{lon:.6f}" hae="0.0" ce="20.0" le="20.0"/>'
        f'<detail>{detail}</detail>'
        f'</event>'
    )


def build_marker_cot(
    *,
    uid: str,
    cot_type: str,
    callsign: str,
    lat: float,
    lon: float,
    now_dt: datetime,
    stale_seconds: int,
    remarks: str,
    side: str,
) -> str:
    time_s = iso_z(now_dt)
    stale_s = iso_z(now_dt + timedelta(seconds=stale_seconds))
    group_name = "Cyan" if side == "blue" else "Red"
    detail = (
        f'<contact callsign="{escape(callsign)}" endpoint="*:-1:stcp"/>'
        f'<__group name="{escape(group_name)}" role="Team Member"/>'
        f'<remarks>{escape(remarks)}</remarks>'
    )
    return (
        f'<event version="2.0" uid="{escape(uid)}" type="{escape(cot_type)}" how="m-g" '
        f'time="{time_s}" start="{time_s}" stale="{stale_s}">'
        f'<point lat="{lat:.6f}" lon="{lon:.6f}" hae="0.0" ce="50.0" le="50.0"/>'
        f'<detail>{detail}</detail>'
        f'</event>'
    )


def event_cot_type(event_type: str) -> str:
    et = str(event_type or "").lower()
    if et == "casualty":
        return "b-d-c"
    if et in ("enemy_sighting", "contact", "troops_in_contact"):
        return "b-m-p-s-p-loc"
    if et in ("alert", "status"):
        return "b-m-p-s-p-op"
    return "b-m-p-s-p-loc"


def event_stale_seconds(event_type: str) -> int:
    et = str(event_type or "").lower()
    if et == "casualty":
        return 1800
    if et in ("alert", "status"):
        return 1800
    return 600


def event_callsign(entity: str, event_type: str) -> str:
    et = str(event_type or "").upper() or "EVENT"
    return f"{entity}-{et}"


def event_remarks(entity: str, event_type: str, meta: Dict[str, Any]) -> str:
    et = str(event_type or "")
    if et == "enemy_sighting":
        target = str(meta.get("target") or "unknown")
        return f"enemy_sighting: {entity} reports {target}"
    if et == "casualty":
        sev = str(meta.get("severity") or "unknown")
        return f"casualty: {entity} severity={sev}"
    if et in ("alert", "status"):
        msg = str(meta.get("message") or "")
        return f"{et}: {entity} {msg}".strip()
    if meta:
        return f"{et}: {entity} {json.dumps(meta, ensure_ascii=False, sort_keys=True)}"
    return f"{et}: {entity}"


def apply_ship_drift(ent: Dict[str, Any], lat: float, lon: float, sim_t: float) -> Tuple[float, float]:
    if str(ent.get("side", "blue")) != "red":
        return lat, lon
    role = str(ent.get("role", ""))
    if "ship" not in role:
        return lat, lon

    phase = (sum(ord(c) for c in str(ent.get("callsign", ""))) % 360) / 57.2958
    east = math.sin(sim_t / 180.0 + phase) * 12.0
    north = math.cos(sim_t / 240.0 + phase) * 6.0
    dlat, dlon = meters_to_latlon_offset(lat, east, north)
    return lat + dlat, lon + dlon


def load_agent_runtime() -> Dict[str, Any]:
    if not AGENT_RUNTIME_JSON.exists():
        return {}
    try:
        return json.loads(AGENT_RUNTIME_JSON.read_text(encoding="utf-8"))
    except Exception:
        return {}


def override_state_from_runtime(
    callsign: str,
    ent: Dict[str, Any],
    base_state: Optional[Dict[str, Any]],
    runtime_by_agent: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    if base_state is None:
        return None

    rt = runtime_by_agent.get(callsign)
    if not isinstance(rt, dict):
        return base_state

    action = str(rt.get("desired_action") or "")
    target = rt.get("target")
    if action not in {"move", "observe", "reposition", "withdraw"}:
        return base_state
    if not isinstance(target, dict) or str(target.get("type") or "") != "point":
        return base_state

    try:
        tgt_lat = float(target["lat"])
        tgt_lon = float(target["lon"])
    except Exception:
        return base_state

    cur_lat = float(base_state["lat"])
    cur_lon = float(base_state["lon"])
    dist_m = haversine_m(cur_lat, cur_lon, tgt_lat, tgt_lon)
    if dist_m < 1.0:
        out = dict(base_state)
        out["activity"] = action
        out["speed_mps"] = 0.0
        return out

    tempo = str(rt.get("tempo") or "static")
    speed_map = {
        "static": 0.0,
        "cautious": 0.6,
        "deliberate": 1.0,
        "urgent": 1.8,
    }
    speed_mps = speed_map.get(tempo, 0.6)

    if action == "observe":
        speed_mps = min(speed_mps, 0.5)
    elif action == "withdraw":
        speed_mps = max(speed_mps, 1.2)

    step_s = 5.0
    move_m = min(dist_m, max(0.0, speed_mps * step_s))
    r = 0.0 if dist_m <= 0 else move_m / dist_m

    new_lat = lerp(cur_lat, tgt_lat, r)
    new_lon = lerp(cur_lon, tgt_lon, r)
    hdg = heading_deg(cur_lat, cur_lon, tgt_lat, tgt_lon)

    out = dict(base_state)
    out["lat"] = new_lat
    out["lon"] = new_lon
    out["heading"] = hdg
    out["speed_mps"] = 0.0 if move_m >= dist_m else speed_mps
    out["activity"] = action
    return out


def state_at(
    scenario: Dict[str, Any],
    callsign: str,
    sim_t: float,
    stack: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    entities = scenario["_entities_by_callsign"]
    tracks = scenario["_tracks_by_callsign"]
    ent = entities[callsign]
    stack = stack or []

    if callsign in stack:
        raise RuntimeError(f"inherit loop detected: {' -> '.join(stack + [callsign])}")

    segs = tracks.get(callsign, [])
    if segs:
        first = segs[0]
        last = segs[-1]

        if sim_t < first.t0:
            lat, lon = first.p0
            lat, lon = apply_ship_drift(ent, lat, lon, sim_t)
            return {
                "lat": lat,
                "lon": lon,
                "activity": "pending",
                "heading": 0.0,
                "speed_mps": 0.0,
            }

        for s in segs:
            if s.t0 <= sim_t <= s.t1:
                dur = max(1e-6, s.t1 - s.t0)
                r = max(0.0, min(1.0, (sim_t - s.t0) / dur))
                lat = lerp(s.p0[0], s.p1[0], r)
                lon = lerp(s.p0[1], s.p1[1], r)
                hdg = heading_deg(s.p0[0], s.p0[1], s.p1[0], s.p1[1]) if (s.p0 != s.p1) else 0.0
                dist_m = haversine_m(s.p0[0], s.p0[1], s.p1[0], s.p1[1])
                speed = dist_m / dur if dur > 0 else 0.0
                lat, lon = apply_ship_drift(ent, lat, lon, sim_t)
                return {
                    "lat": lat,
                    "lon": lon,
                    "activity": s.activity,
                    "heading": hdg,
                    "speed_mps": speed,
                }

        lat, lon = last.p1
        lat, lon = apply_ship_drift(ent, lat, lon, sim_t)
        return {
            "lat": lat,
            "lon": lon,
            "activity": last.activity or "hold",
            "heading": 0.0,
            "speed_mps": 0.0,
        }

    parent = ent.get("inherit")
    if parent and parent in entities:
        parent_state = state_at(scenario, parent, sim_t, stack + [callsign])
        if parent_state is None:
            return None

        east_m, north_m = 0.0, 0.0
        if isinstance(ent.get("offset_m"), list) and len(ent["offset_m"]) == 2:
            east_m = float(ent["offset_m"][0])
            north_m = float(ent["offset_m"][1])

        east_m, north_m = rotate_offset(east_m, north_m, float(parent_state["heading"]))
        dlat, dlon = meters_to_latlon_offset(parent_state["lat"], east_m, north_m)
        return {
            "lat": parent_state["lat"] + dlat,
            "lon": parent_state["lon"] + dlon,
            "activity": parent_state["activity"],
            "heading": parent_state["heading"],
            "speed_mps": parent_state["speed_mps"],
        }

    return None


def synthesize_orbat_entities(spec: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not spec or not spec.get("enabled"):
        return []

    out: List[Dict[str, Any]] = []
    battalion_fal = str(spec.get("battalion", "VQ")).upper()
    companies = [str(x).upper() for x in spec.get("companies", [])]
    platoons = [str(x).upper() for x in spec.get("platoons", [])]
    groups = [str(x).upper() for x in spec.get("groups", [])]
    individuals_per_group = int(spec.get("individuals_per_group", 0))

    out.append({
        "callsign": battalion_fal,
        "side": "blue",
        "role": "battalion",
    })

    for company_fal in companies:
        company_letter = company_fal[:1]
        company_falfal = f"{company_fal}{battalion_fal}"
        out.append({
            "callsign": company_falfal,
            "side": "blue",
            "role": "company",
            "inherit": battalion_fal,
        })

        for platoon_letter in platoons:
            platoon_fal = f"{platoon_letter}{company_letter}"
            platoon_falfal = f"{platoon_fal}{company_fal}"
            out.append({
                "callsign": platoon_falfal,
                "side": "blue",
                "role": "platoon",
                "inherit": company_falfal,
            })

            for group_letter in groups:
                group_fal = f"{group_letter}{platoon_letter}"
                group_falfal = f"{group_fal}{company_fal}"
                out.append({
                    "callsign": group_falfal,
                    "side": "blue",
                    "role": "group",
                    "inherit": platoon_falfal,
                })

                for i in range(1, individuals_per_group + 1):
                    out.append({
                        "callsign": f"{group_falfal}{i}",
                        "side": "blue",
                        "role": "individual",
                        "inherit": group_falfal,
                    })

    return out


def load_scenario_from_data(data: Dict[str, Any]) -> Dict[str, Any]:
    entities = {e["callsign"]: e for e in data.get("entities", [])}
    tracks: Dict[str, List[Segment]] = {}

    for t in data.get("tracks", []):
        callsign = t["entity"]
        segs: List[Segment] = []
        for s in t.get("segments", []):
            segs.append(
                Segment(
                    t0=float(s["t0"]),
                    t1=float(s["t1"]),
                    p0=(float(s["from"][0]), float(s["from"][1])),
                    p1=(float(s["to"][0]), float(s["to"][1])),
                    activity=str(s.get("activity", "")),
                )
            )
        tracks[callsign] = segs

    for cs, ent in entities.items():
        ent.setdefault("uid", entity_uid(data["scenario_id"], cs))
        ent.setdefault("side", "blue")
        ent.setdefault("role", "unit")
        if "inherit" not in ent:
            parent = auto_inherit(cs)
            if parent and parent in entities:
                ent["inherit"] = parent
        ent["_fal"] = classify_blue(cs) if ent["side"] == "blue" else {}
        ent.setdefault("cot_type", default_cot_type(ent))
        if ent["side"] == "blue" and ent.get("inherit") and "offset_m" not in ent:
            e_m, n_m = formation_offset_from_suffix(cs)
            ent["offset_m"] = [e_m, n_m]

    data.setdefault("contact_rules", [])
    data.setdefault("auto_orbat", {})
    data["_entities_by_callsign"] = entities
    data["_tracks_by_callsign"] = tracks
    data["_events"] = sorted(data.get("events", []), key=lambda x: float(x.get("t", 0)))
    return data


class UdpCotEmitter:
    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def send(self, xml_text: str) -> None:
        self.sock.sendto(xml_text.encode("utf-8"), (self.host, self.port))


def maybe_emit_contact_events(
    *,
    scenario: Dict[str, Any],
    states: Dict[str, Dict[str, Any]],
    entities: Dict[str, Dict[str, Any]],
    frame_now: datetime,
    emitter: UdpCotEmitter,
    sent_contact_keys: set[str],
) -> None:
    rules = scenario.get("contact_rules", [])
    for rule in rules:
        blue_prefixes = [str(x) for x in rule.get("blue_prefixes", [])]
        red_prefixes = [str(x) for x in rule.get("red_prefixes", [])]
        range_m = float(rule.get("range_m", 5000))
        remarks = str(rule.get("remarks", "enemy sighting"))

        blues = [
            cs for cs, ent in entities.items()
            if str(ent.get("side", "blue")) == "blue"
            and any(cs.startswith(p) for p in blue_prefixes)
            and cs in states
        ]
        reds = [
            cs for cs, ent in entities.items()
            if str(ent.get("side", "blue")) == "red"
            and any(cs.startswith(p) for p in red_prefixes)
            and cs in states
        ]

        for b in blues:
            for r in reds:
                sb = states[b]
                sr = states[r]
                d = haversine_m(sb["lat"], sb["lon"], sr["lat"], sr["lon"])
                if d > range_m:
                    continue

                key = f"{b}|{r}|{int(frame_now.timestamp()) // 300}"
                if key in sent_contact_keys:
                    continue
                sent_contact_keys.add(key)

                uid = f"replay:{scenario['scenario_id']}:contact:{b}:{r}"
                xml_text = build_marker_cot(
                    uid=uid,
                    cot_type="b-m-p-s-p-loc",
                    callsign=f"{b}-CONTACT",
                    lat=sb["lat"],
                    lon=sb["lon"],
                    now_dt=frame_now,
                    stale_seconds=180,
                    remarks=f"{remarks}: {b} sees {r} at {int(d)}m",
                    side="blue",
                )
                emitter.send(xml_text)
                print(f"[auto-contact] {b} -> {r} dist={int(d)}m")


def maybe_emit_scenario_event(
    *,
    scenario: Dict[str, Any],
    entities: Dict[str, Dict[str, Any]],
    frame_states: Dict[str, Dict[str, Any]],
    frame_now: datetime,
    emitter: UdpCotEmitter,
    ev: Dict[str, Any],
) -> None:
    entity = str(ev.get("entity") or "")
    event_type = str(ev.get("type") or "event")
    meta = ev.get("meta") or {}

    ent = entities.get(entity, {})
    st = frame_states.get(entity)
    if st is None and entity in entities:
        st = {"lat": 0.0, "lon": 0.0}
    if st is None:
        return

    side = str(ent.get("side", "blue")) if ent else "blue"
    uid = f"replay:{scenario['scenario_id']}:event:{entity}:{event_type}:{int(float(ev.get('t', 0)))}"
    xml_text = build_marker_cot(
        uid=uid,
        cot_type=event_cot_type(event_type),
        callsign=event_callsign(entity, event_type),
        lat=float(st["lat"]),
        lon=float(st["lon"]),
        now_dt=frame_now,
        stale_seconds=event_stale_seconds(event_type),
        remarks=event_remarks(entity, event_type, meta),
        side=side,
    )
    emitter.send(xml_text)


def cleanup_replay_rows(dbname: str = "cot") -> None:
    sql = "DELETE FROM cot_router WHERE uid LIKE 'replay:%';"
    res = subprocess.run(
        ["sudo", "-u", "postgres", "psql", "-d", dbname, "-P", "pager=off", "-c", sql],
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode != 0:
        msg = (res.stderr or res.stdout or "").strip()
        raise RuntimeError(f"replay cleanup failed: {msg}")
    out = (res.stdout or "").strip().replace("\n", " | ")
    if out:
        print(f"[cleanup] {out}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", required=True, help="Path to scenario.json")
    ap.add_argument("--host", default=os.environ.get("TAK_REPLAY_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("TAK_REPLAY_PORT", "6969")))
    ap.add_argument("--speed", type=float, default=60.0, help="Scenario seconds per real second")
    ap.add_argument("--duration", type=float, default=14400.0, help="Scenario duration in seconds")
    ap.add_argument("--once", action="store_true", help="Emit one frame only")
    ap.add_argument("--callsigns", default="", help="Optional comma-separated subset of callsigns to emit")
    ap.add_argument("--dump-auto-orbat", action="store_true", help="Print synthesized ORBAT and exit")
    ap.add_argument("--no-cleanup", action="store_true", help="Do not delete old replay:* rows on startup")
    args = ap.parse_args()

    scenario_path = Path(args.scenario)
    with scenario_path.open("r", encoding="utf-8") as f:
        raw_data = json.load(f)

    auto_entities = synthesize_orbat_entities(raw_data.get("auto_orbat", {}))
    if auto_entities:
        existing = {e["callsign"] for e in raw_data.get("entities", [])}
        for e in auto_entities:
            if e["callsign"] not in existing:
                raw_data.setdefault("entities", []).append(e)

    if args.dump_auto_orbat:
        print(json.dumps(raw_data.get("entities", []), ensure_ascii=False, indent=2))
        return

    if not args.no_cleanup:
        cleanup_replay_rows()

    scenario = load_scenario_from_data(raw_data)

    tick = float(scenario.get("tick_seconds", 5))
    stale_seconds = int(scenario.get("default_stale_seconds", 90))
    emitter = UdpCotEmitter(args.host, args.port)

    scenario_id = scenario["scenario_id"]
    entities = scenario["_entities_by_callsign"]
    events = scenario["_events"]
    event_idx = 0
    sent_contact_keys: set[str] = set()

    selected: Optional[set[str]] = None
    if args.callsigns.strip():
        selected = {x.strip() for x in args.callsigns.split(",") if x.strip()}

    wall_start = time.time()
    sim_start = datetime.now(timezone.utc)

    while True:
        now_wall = time.time()
        sim_t = (now_wall - wall_start) * args.speed
        if sim_t > args.duration:
            break

        frame_now = sim_start + timedelta(seconds=sim_t)
        frame_states: Dict[str, Dict[str, Any]] = {}
        runtime_by_agent = load_agent_runtime()

        for cs in sorted(entities.keys()):
            if selected is not None and cs not in selected:
                continue

            ent = entities[cs]
            st = state_at(scenario, cs, sim_t)
            st = override_state_from_runtime(cs, ent, st, runtime_by_agent)
            if st is None:
                continue
            frame_states[cs] = st

            xml_text = build_cot(
                uid=ent["uid"],
                cot_type=ent["cot_type"],
                callsign=cs,
                lat=st["lat"],
                lon=st["lon"],
                activity=st["activity"],
                now_dt=frame_now,
                stale_seconds=stale_seconds,
                speed_mps=st["speed_mps"],
                heading=st["heading"],
                role=str(ent.get("role", "unit")),
                side=str(ent.get("side", "blue")),
                ent=ent,
            )
            emitter.send(xml_text)

        maybe_emit_contact_events(
            scenario=scenario,
            states=frame_states,
            entities=entities,
            frame_now=frame_now,
            emitter=emitter,
            sent_contact_keys=sent_contact_keys,
        )

        while event_idx < len(events) and float(events[event_idx].get("t", 0)) <= sim_t:
            ev = events[event_idx]
            maybe_emit_scenario_event(
                scenario=scenario,
                entities=entities,
                frame_states=frame_states,
                frame_now=frame_now,
                emitter=emitter,
                ev=ev,
            )
            meta = ev.get("meta", {})
            print(
                f"[event scenario={scenario_id} t={ev.get('t')}] "
                f"entity={ev.get('entity')} type={ev.get('type')} meta={json.dumps(meta, ensure_ascii=False)}"
            )
            event_idx += 1

        if args.once:
            break

        time.sleep(tick)

    print("done")


if __name__ == "__main__":
    main()
