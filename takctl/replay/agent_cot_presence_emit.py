from __future__ import annotations

import argparse
import json
import socket
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List
from xml.sax.saxutils import escape

from replay_paths import STATE_ROOT


def agent_dir(callsign: str) -> Path:
    return STATE_ROOT / "agents" / callsign


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    txt = path.read_text(encoding="utf-8").strip()
    if not txt:
        return {}
    return json.loads(txt)


def iter_agent_dirs() -> List[Path]:
    root = STATE_ROOT / "agents"
    out: List[Path] = []
    if not root.exists():
        return out
    for p in sorted(root.iterdir()):
        if p.is_dir() and (p / "state.json").exists():
            out.append(p)
    return out


def iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def cot_type_for_role(role: str) -> str:
    role = str(role or "")
    if role == "battalion":
        return "a-f-G-U-C"
    if role == "company":
        return "a-f-G-U-C"
    if role in {"platoon", "staff_tross_platoon"}:
        return "a-f-G-U-C"
    if role == "group":
        return "a-f-G-U-C"
    return "a-f-G-U-C"


def role_name_sv(role: str) -> str:
    role = str(role or "")
    return {
        "battalion": "Bataljon",
        "company": "Kompani",
        "platoon": "Pluton",
        "staff_tross_platoon": "Stab/Trosspluton",
        "group": "Grupp",
        "group_leader": "Gruppchef",
        "assistant_group_leader": "Stf gruppchef",
        "soldier": "Soldat",
    }.get(role, role or "Enhet")


def current_action_from_work(st: Dict[str, Any]) -> str:
    for chain in list(st.get("work") or []):
        if not isinstance(chain, list) or not chain:
            continue
        root = dict(chain[0] or {})
        kind = str(root.get("kind") or "")
        if kind == "execute_action":
            return str(root.get("action") or "")
    return ""


def current_target_from_work(st: Dict[str, Any]) -> str:
    for chain in list(st.get("work") or []):
        if not isinstance(chain, list) or not chain:
            continue
        root = dict(chain[0] or {})
        kind = str(root.get("kind") or "")
        if kind != "execute_action":
            continue
        target = root.get("target")
        if not isinstance(target, dict):
            return ""
        ttype = str(target.get("type") or "")
        if ttype == "area":
            return str(target.get("name") or "")
        if ttype == "unit":
            return str(target.get("callsign") or "")
        if ttype == "point":
            lat = target.get("lat")
            lon = target.get("lon")
            if lat is not None and lon is not None:
                return f"{lat},{lon}"
    return ""


def posture_sv(own_posture: Any) -> str:
    v = str(own_posture or "").strip()
    if not v:
        return "okänt läge"
    return v


def build_presence_cot(st: Dict[str, Any], now_dt: datetime) -> str | None:
    agent = dict(st.get("agent") or {})
    own = dict(st.get("own_state") or {})

    callsign = str(agent.get("callsign") or "").strip()
    if not callsign:
        return None

    pos = dict(own.get("position") or {})
    lat = pos.get("lat")
    lon = pos.get("lon")
    if lat is None or lon is None:
        return None

    try:
        lat_f = float(lat)
        lon_f = float(lon)
    except Exception:
        return None

    role = str(agent.get("role") or "")
    uid = f"replay:presence:{callsign}"
    time_s = iso_z(now_dt)
    stale_s = iso_z(now_dt + timedelta(minutes=10))
    cot_type = cot_type_for_role(role)

    readiness = str(own.get("readiness") or "")
    combat_value = str(own.get("combat_value") or "")
    strength = own.get("strength")
    own_posture = own.get("posture")
    psv = posture_sv(own_posture)
    action = current_action_from_work(st)
    target = current_target_from_work(st)
    superior = str(agent.get("superior") or "")

    remarks_bits = [
        f"{role_name_sv(role)}",
        f"läge {psv}",
    ]
    if readiness:
        remarks_bits.append(f"beredskap {readiness}")
    if combat_value:
        remarks_bits.append(f"stridsvärde {combat_value}")
    if strength not in (None, ""):
        remarks_bits.append(f"styrka {strength}")
    if action:
        remarks_bits.append(f"uppgift {action}")
    if target:
        remarks_bits.append(f"mål {target}")
    if superior:
        remarks_bits.append(f"chef {superior}")

    remarks = ". ".join(remarks_bits) + "."

    return (
        f'<event version="2.0" uid="{escape(uid)}" type="{escape(cot_type)}" how="m-g" '
        f'time="{time_s}" start="{time_s}" stale="{stale_s}">'
        f'<point lat="{lat_f:.6f}" lon="{lon_f:.6f}" hae="0.0" ce="50.0" le="50.0"/>'
        f'<detail>'
        f'<contact callsign="{escape(callsign)}" endpoint="*:-1:stcp"/>'
        f'<__group name="Blue" role="Team Member"/>'
        f'<status readiness="{escape(readiness)}" combat_value="{escape(combat_value)}"/>'
        f'<remarks>{escape(remarks)}</remarks>'
        f'</detail>'
        f'</event>'
    )


def send_udp(xml_text: str, host: str, port: int) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.sendto(xml_text.encode("utf-8"), (host, port))
    finally:
        sock.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--callsigns", default="", help="comma-separated subset; default all")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=6969)
    args = ap.parse_args()

    selected = None
    if args.callsigns.strip():
        selected = {x.strip().upper() for x in args.callsigns.split(",") if x.strip()}

    now_dt = datetime.now(timezone.utc)
    sent = 0

    for d in iter_agent_dirs():
        st = read_json(d / "state.json")
        callsign = str((st.get("agent") or {}).get("callsign") or d.name).upper()
        if selected is not None and callsign not in selected:
            continue

        xml_text = build_presence_cot(st, now_dt)
        if not xml_text:
            continue

        send_udp(xml_text, args.host, args.port)
        sent += 1

    print(f"sent={sent}")


if __name__ == "__main__":
    main()
