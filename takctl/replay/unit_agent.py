from __future__ import annotations

import argparse
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List

from llm_decision import build_agent_packet, parse_and_validate
from llm_runner import run_model
from prompting import write_prompt_log
from replay_paths import agent_dir, ensure_runtime_dirs
from tasking import decision_to_work


def ensure_agent_layout(callsign: str) -> Path:
    d = agent_dir(callsign)
    d.mkdir(parents=True, exist_ok=True)
    for name, default in [
        ("state.json", {}),
        ("inbox.jsonl", None),
        ("outbox.jsonl", None),
        ("decisions.jsonl", None),
        ("tasks.jsonl", None),
    ]:
        p = d / name
        if not p.exists():
            if name.endswith(".json"):
                p.write_text(json.dumps(default, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            else:
                p.write_text("", encoding="utf-8")
    return d


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    txt = path.read_text(encoding="utf-8").strip()
    if not txt:
        return {}
    return json.loads(txt)


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_jsonl(path: Path, obj: Dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        out.append(json.loads(line))
    return out


def overwrite_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def tail_list(rows: List[Dict[str, Any]], n: int = 20) -> List[Dict[str, Any]]:
    return rows[-n:]


def has_work(st: Dict[str, Any]) -> bool:
    work = st.get("work")
    if not isinstance(work, list):
        return False
    for chain in work:
        if isinstance(chain, list) and chain:
            return True
    return False


def ensure_memory_fields(st: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(st, dict):
        st = {}
    st.setdefault("agent", {})
    st.setdefault("own_state", {})
    st.setdefault("subordinates", [])
    st.setdefault("observations", [])
    st.setdefault("constraints", {})
    st.setdefault("work", [])
    st.setdefault("completed_work", [])
    return st




def seed_state_if_empty(callsign: str, role: str, superior: str, mission: str) -> None:
    d = ensure_agent_layout(callsign)
    p = d / "state.json"
    st = read_json(p)
    if st:
        return

    st = {
        "agent": {
            "callsign": callsign,
            "role": role,
            "side": "blue",
            "superior": superior,
            "mission": mission,
        },
        "own_state": {
            "position": {"lat": 55.4220, "lon": 13.9180},
            "strength": 24 if role == "platoon" else 8,
            "ammo": "adequate",
            "morale": "steady",
            "posture": "screening",
        },
        "subordinates": [],
        "observations": [],
        "constraints": {
            "roe": "defensive",
            "decision_horizon_sec": 300,
        },
        "work": [],
        "completed_work": [],
    }
    write_json(p, st)


def ingest_inbox_into_state(callsign: str) -> Dict[str, Any]:
    d = ensure_agent_layout(callsign)
    state_path = d / "state.json"
    st = ensure_memory_fields(read_json(state_path))
    write_json(state_path, st)
    return st






def _geo_cache_path(st: Dict[str, Any]) -> Path | None:
    agent = dict(st.get("agent") or {})
    callsign = str(agent.get("callsign") or "").strip()
    if not callsign:
        return None
    return agent_dir(callsign) / "geo_cache.json"


def _read_geo_cache(st: Dict[str, Any], max_age_s: int = 3600) -> Dict[str, Any] | None:
    p = _geo_cache_path(st)
    if p is None or not p.exists():
        return None
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    ts = float(obj.get("_cached_at") or 0)
    if ts <= 0 or (time.time() - ts) > max_age_s:
        return None
    data = obj.get("data")
    if isinstance(data, dict):
        data = dict(data)
        data.setdefault("source", {})
        if isinstance(data["source"], dict):
            data["source"]["cache"] = "hit"
        return data
    return None


def _write_geo_cache(st: Dict[str, Any], data: Dict[str, Any]) -> None:
    p = _geo_cache_path(st)
    if p is None:
        return
    payload = {
        "_cached_at": time.time(),
        "data": data,
    }
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _geo_area_summary_for_state(st: Dict[str, Any]) -> Dict[str, Any]:
    own = dict(st.get("own_state") or {})
    pos = dict(own.get("position") or {})
    lat = pos.get("lat")
    lon = pos.get("lon")
    if lat is None or lon is None:
        return {"ok": False, "error": "missing_position"}

    params = urllib.parse.urlencode({
        "lat": str(lat),
        "lon": str(lon),
        "radius_m": "1000",
    })
    url = f"http://127.0.0.1:8080/api/geo/area_summary?{params}"

    try:
        with urllib.request.urlopen(url, timeout=3.0) as r:
            raw = (r.read() or b"").decode("utf-8", "replace")
        data = json.loads(raw)
        if isinstance(data, dict) and data.get("ok"):
            _write_geo_cache(st, data)
            return data
        cached = _read_geo_cache(st)
        if cached is not None:
            return cached
        if isinstance(data, dict):
            return data
        return {"ok": False, "error": "invalid_geo_payload"}
    except Exception as e:
        cached = _read_geo_cache(st)
        if cached is not None:
            cached = dict(cached)
            cached["warning"] = f"live_geo_failed_using_cache: {e}"
            return cached
        return {"ok": False, "error": f"geo_lookup_failed: {e}"}


def _geo_area_brief(local_area: Dict[str, Any], language_profile: str) -> Dict[str, Any]:
    lang = "sv" if str(language_profile or "").strip().lower().startswith("sv") else "en"

    if not isinstance(local_area, dict) or not local_area.get("ok"):
        return {
            "ok": False,
            "language": lang,
            "summary_text": (
                "Ingen geografisk områdessammanfattning tillgänglig."
                if lang == "sv" else
                "No geographic area summary available."
            ),
        }

    def tr_mob(v: str) -> str:
        key = str(v or "").strip()
        if lang == "sv":
            m = {
                "good": "god",
                "mixed": "blandad",
                "limited": "begränsad",
                "restricted": "mycket begränsad",
                "good_on_roads": "god på väg",
                "good_on_roads_limited_offroad": "god på väg, begränsad terrängframkomlighet",
            }
            return m.get(key, key or "okänd")
        m = {
            "god": "good",
            "blandad": "mixed",
            "begränsad": "limited",
            "mycket begränsad": "restricted",
        }
        return m.get(key, key or "unknown")

    def tr_text(v: str) -> str:
        t = str(v or "").strip()
        sv = {
            "approach routes appear limited and exposed": "framryckningsvägarna bedöms vara få och exponerade",
            "few obvious observation positions detected": "få tydliga observationslägen identifierade",
            "open ground exposure": "öppen mark medför exponering",
            "road approach likely": "framryckning längs väg är sannolik",
            "foot infiltration via tracks/paths possible": "infiltration till fots via stigar och mindre vägar möjlig",
            "covered movement through built-up area possible": "skyddad framryckning genom bebyggelse möjlig",
            "concealed movement via tree cover possible": "dold framryckning via trädbevuxen terräng möjlig",
            "built-up edge positions": "läge i bebyggelsekant",
            "tree line / woodland edge": "läge i skogsbryn eller trädlinje",
            "waterfront observation line": "observationslinje längs strand eller vatten",
            "road junction overwatch": "övervakning av vägkorsning",
            "water obstacle / exposed shoreline": "vattenhinder eller exponerad strandlinje",
            "road crossing / avenue of approach": "vägövergång eller sannolik anfallsriktning",
            "terrain appears mixed with no single dominant risk area": "terrängen är blandad utan en tydligt dominerande riskyta",
        }
        en = {v: k for k, v in sv.items()}
        if lang == "sv":
            return sv.get(t, t)
        return en.get(t, t)

    def tr_label(label: str) -> str:
        t = str(label or "").strip()
        if lang == "sv":
            return t.replace("(nature_reserve)", "(naturreservat)")
        return t.replace("(naturreservat)", "(nature_reserve)")

    mobility = dict(local_area.get("mobility") or {})
    ta = dict(local_area.get("tactical_assessment") or {})

    named = [tr_label(x) for x in list(local_area.get("named_pois") or [])]
    likely = [tr_text(x) for x in list(ta.get("likely_approach_routes") or [])]
    op = [tr_text(x) for x in list(ta.get("good_op_positions") or [])]
    risks = [tr_text(x) for x in list(ta.get("risk_areas") or [])]

    mobility_i18n = {
        "foot": tr_mob(mobility.get("foot")),
        "vehicle": tr_mob(mobility.get("vehicle")),
        "concealment": tr_mob(mobility.get("concealment")),
        "observation": tr_mob(mobility.get("observation")),
    }

    parts = []
    if lang == "sv":
        if named:
            parts.append("Viktiga terrängföremål: " + ", ".join(named[:3]))
        parts.append(
            "Framkomlighet och terräng: fot="
            + mobility_i18n["foot"]
            + ", fordon="
            + mobility_i18n["vehicle"]
            + ", skydd="
            + mobility_i18n["concealment"]
            + ", observation="
            + mobility_i18n["observation"]
        )
        if likely:
            parts.append("Sannolika framryckningsvägar: " + "; ".join(likely[:2]))
        if op:
            parts.append("Lämpliga observationslägen: " + "; ".join(op[:2]))
        if risks:
            parts.append("Riskytor: " + "; ".join(risks[:2]))
        summary_text = " | ".join(parts) if parts else "Ingen tydlig terrängbedömning tillgänglig."
    else:
        if named:
            parts.append("Key terrain features: " + ", ".join(named[:3]))
        parts.append(
            "Mobility and terrain: foot="
            + mobility_i18n["foot"]
            + ", vehicle="
            + mobility_i18n["vehicle"]
            + ", concealment="
            + mobility_i18n["concealment"]
            + ", observation="
            + mobility_i18n["observation"]
        )
        if likely:
            parts.append("Likely approach routes: " + "; ".join(likely[:2]))
        if op:
            parts.append("Suitable observation positions: " + "; ".join(op[:2]))
        if risks:
            parts.append("Risk areas: " + "; ".join(risks[:2]))
        summary_text = " | ".join(parts) if parts else "No clear terrain assessment available."

    return {
        "ok": True,
        "language": lang,
        "named_features": named[:6],
        "mobility": mobility_i18n,
        "likely_approach_routes": likely[:4],
        "good_op_positions": op[:4],
        "risk_areas": risks[:4],
        "summary_text": summary_text,
    }

def build_packet_from_state(st: Dict[str, Any], sim_time_s: int) -> Dict[str, Any]:
    agent = dict(st.get("agent") or {})
    callsign = str(agent.get("callsign") or "").strip()
    inbox_rows = []
    if callsign:
        inbox_rows = read_jsonl(agent_dir(callsign) / "inbox.jsonl")

    packet = build_agent_packet(
        sim_time_s=sim_time_s,
        agent=agent,
        own_state=dict(st.get("own_state") or {}),
        subordinates=list(st.get("subordinates") or []),
        observations=list(st.get("observations") or []),
        constraints=dict(st.get("constraints") or {}),
    )
    packet["inbox"] = inbox_rows
    packet["work"] = list(st.get("work") or [])
    packet["completed_work"] = list(st.get("completed_work") or [])
    local_area = _geo_area_summary_for_state(st)
    packet["geo"] = {
        "local_area": local_area,
        "local_area_brief": _geo_area_brief(local_area, str(agent.get("language_profile") or "")),
    }
    return packet


def load_model_response(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def append_completed_work(st: Dict[str, Any], item: Dict[str, Any]) -> None:
    completed = list(st.get("completed_work") or [])
    completed.append(item)
    st["completed_work"] = completed[-200:]


def emit_message_action(
    callsign: str,
    item: Dict[str, Any],
    sim_time_s: int,
    outbox_path: Path,
    st: Dict[str, Any],
) -> None:
    params = dict(item.get("params") or {})
    recipient = str(params.get("recipient") or "").strip()
    message = str(params.get("message") or "").strip()
    if not recipient or not message:
        return

    meta = {
        "action": item.get("action"),
        "title": item.get("title"),
    }

    msg = {
        "kind": "message",
        "from": callsign,
        "to": recipient,
        "sim_time_s": int(sim_time_s),
        "message": message,
        "meta": meta,
    }
    append_jsonl(outbox_path, msg)


def emit_report_up(
    callsign: str,
    superior: str,
    item: Dict[str, Any],
    sim_time_s: int,
    outbox_path: Path,
    st: Dict[str, Any],
) -> None:
    if not superior:
        return

    message = str(item.get("message") or "").strip()
    if not message:
        return

    meta = dict(item.get("meta") or {})
    msg = {
        "kind": "status_report",
        "from": callsign,
        "to": superior,
        "sim_time_s": int(sim_time_s),
        "message": message,
        "meta": meta,
    }
    append_jsonl(outbox_path, msg)


def _complete_root(st: Dict[str, Any], root: Dict[str, Any], sim_time_s: int) -> None:
    root["status"] = "completed"
    root["completed_sim_time_s"] = int(sim_time_s)
    append_completed_work(st, root)


def _execute_move_unit(st: Dict[str, Any], root: Dict[str, Any], sim_time_s: int) -> None:
    params = dict(root.get("params") or {})
    own = st.setdefault("own_state", {})
    pos = dict(own.get("position") or {})

    lat = params.get("lat", params.get("destination_lat"))
    lon = params.get("lon", params.get("destination_lon"))
    if lat is None or lon is None:
        return

    try:
        pos["lat"] = float(lat)
        pos["lon"] = float(lon)
    except Exception:
        return

    own["position"] = pos
    urgency = str(params.get("urgency") or params.get("movement_type") or "").strip()
    if urgency:
        own["last_movement"] = {
            "sim_time_s": int(sim_time_s),
            "urgency": urgency,
        }


def _execute_change_posture(st: Dict[str, Any], root: Dict[str, Any], sim_time_s: int) -> None:
    params = dict(root.get("params") or {})
    posture = str(params.get("posture") or "").strip()
    if not posture:
        return
    own = st.setdefault("own_state", {})
    own["posture"] = posture
    own["posture_updated_sim_time_s"] = int(sim_time_s)


def _execute_hold_position(st: Dict[str, Any], root: Dict[str, Any], sim_time_s: int) -> None:
    params = dict(root.get("params") or {})
    own = st.setdefault("own_state", {})
    pos = dict(own.get("position") or {})
    lat = params.get("lat")
    lon = params.get("lon")
    try:
        if lat is not None:
            pos["lat"] = float(lat)
        if lon is not None:
            pos["lon"] = float(lon)
    except Exception:
        pass
    own["position"] = pos
    own["holding_since_sim_time_s"] = int(sim_time_s)


def _execute_observe_area(st: Dict[str, Any], root: Dict[str, Any], sim_time_s: int) -> None:
    params = dict(root.get("params") or {})
    obs = list(st.get("observations") or [])
    center_lat = params.get("center_lat", params.get("lat"))
    center_lon = params.get("center_lon", params.get("lon"))
    radius_km = params.get("radius_km", params.get("radius"))
    focus = params.get("focus") or []

    row = {
        "kind": "area_observation_task",
        "sim_time_s": int(sim_time_s),
        "from": str((st.get("agent") or {}).get("callsign") or ""),
        "center": {
            "lat": center_lat,
            "lon": center_lon,
        },
        "radius_km": radius_km,
        "focus": focus,
        "summary": str(root.get("description") or root.get("title") or "observe_area"),
    }
    obs.append(row)
    st["observations"] = obs[-200:]


def inbox_count_for_callsign(callsign: str) -> int:
    d = ensure_agent_layout(callsign)
    inbox = read_jsonl(d / "inbox.jsonl")
    return len(inbox)


def world_changed(st: Dict[str, Any], sim_time_s: int) -> bool:
    del st
    del sim_time_s
    return False


def llm_trigger_reason(
    st: Dict[str, Any],
    callsign: str,
    sim_time_s: int,
    completed_before: int,
    completed_after: int,
) -> str:
    if inbox_count_for_callsign(callsign) > 0:
        return "inbox"
    if completed_after > completed_before:
        return "deadline"
    if world_changed(st, sim_time_s):
        return "world_change"
    return ""


def process_work(st: Dict[str, Any], sim_time_s: int, outbox_path: Path) -> int:
    callsign = str((st.get("agent") or {}).get("callsign") or "")
    superior = str((st.get("agent") or {}).get("superior") or "")

    new_work: List[List[Dict[str, Any]]] = []
    for chain in list(st.get("work") or []):
        if not isinstance(chain, list) or not chain:
            continue

        chain = [dict(x or {}) for x in chain if isinstance(x, dict)]
        if not chain:
            continue

        root = chain[0]
        rest = chain[1:]

        action = str(root.get("action") or "")
        status = str(root.get("status") or "")
        deadline = int(root.get("deadline_sim_time_s") or 0)

        if status == "pending":
            root["status"] = "active"
            root["started_sim_time_s"] = int(sim_time_s)
            if not root.get("deadline_sim_time_s"):
                root["deadline_sim_time_s"] = int(sim_time_s) + int(root.get("duration_s") or 0)
            deadline = int(root.get("deadline_sim_time_s") or 0)

            if action == "move_unit":
                _execute_move_unit(st, root, sim_time_s)
            elif action == "change_posture":
                _execute_change_posture(st, root, sim_time_s)
            elif action == "observe_area":
                _execute_observe_area(st, root, sim_time_s)
            elif action == "hold_position":
                _execute_hold_position(st, root, sim_time_s)

        completed_now = False

        if action == "send_message":
            emit_message_action(callsign, root, sim_time_s, outbox_path, st)
            _complete_root(st, root, sim_time_s)
            completed_now = True

        elif action == "report_status":
            params = dict(root.get("params") or {})
            recipient = str(params.get("recipient") or superior).strip()
            root["message"] = str(params.get("message") or "")
            emit_report_up(callsign, recipient, root, sim_time_s, outbox_path, st)
            _complete_root(st, root, sim_time_s)
            completed_now = True

        elif action in {
            "llm_replan_from_inbox",
            "llm_replan_from_deadline",
            "llm_replan_from_world_change",
            "move_unit",
            "change_posture",
            "observe_area",
            "hold_position",
        }:
            if deadline and int(sim_time_s) >= deadline:
                _complete_root(st, root, sim_time_s)
                completed_now = True

        if completed_now:
            if rest:
                nxt = dict(rest[0] or {})
                if not nxt.get("status") or str(nxt.get("status")) == "completed":
                    nxt["status"] = "pending"
                if nxt.get("created_sim_time_s") is None:
                    nxt["created_sim_time_s"] = int(sim_time_s)
                new_work.append([nxt] + rest[1:])
        else:
            new_work.append([root] + rest)

    st["work"] = new_work
    return len(list(st.get("completed_work") or []))

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--callsign", required=True)
    ap.add_argument("--role", default="platoon")
    ap.add_argument("--superior", default="TQVQ")
    ap.add_argument("--mission", default="Delay enemy approach east of Ystad")
    ap.add_argument("--sim-time", type=int, default=2100)
    ap.add_argument("--model-response", default="")
    ap.add_argument("--live-llm", action="store_true")
    ap.add_argument("--temperature", type=float, default=0.2)
    ap.add_argument("--max-tokens", type=int, default=300)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    ensure_runtime_dirs()

    d = ensure_agent_layout(args.callsign)
    seed_state_if_empty(args.callsign, args.role, args.superior, args.mission)

    st = ingest_inbox_into_state(args.callsign)
    st = ensure_memory_fields(st)

    outbox_path = d / "outbox.jsonl"

    completed_before = len(list(st.get("completed_work") or []))

    # Kör roten på varje arbetskedja en gång per tick
    completed_after = process_work(st, args.sim_time, outbox_path)

    trigger = llm_trigger_reason(
        st=st,
        callsign=args.callsign,
        sim_time_s=args.sim_time,
        completed_before=completed_before,
        completed_after=completed_after,
    )

    if not trigger:
        write_json(d / "state.json", st)
        return

    packet = build_packet_from_state(st, args.sim_time)
    packet["llm_trigger_reason"] = trigger

    if args.live_llm:
        write_json(d / "state.json", st)
        try:
            llm_result = run_model(
                packet=packet,
                temperature=args.temperature,
                max_tokens=args.max_tokens,
                seed=args.seed,
            )
            raw_text = llm_result.get("text") or ""
        finally:
            write_json(d / "state.json", st)
    else:
        if not args.model_response:
            raise RuntimeError("either --live-llm or --model-response is required")
        raw_text = load_model_response(Path(args.model_response))
        llm_result = {
            "ok": True,
            "provider": "file",
            "model": "file",
            "url": str(args.model_response),
            "http_status": None,
            "body_bytes": len(raw_text.encode("utf-8")),
            "error": None,
        }

    write_prompt_log(d, packet, raw_text)
    result = parse_and_validate(raw_text, packet)

    new_work = decision_to_work(
        decision=result.decision,
        sim_time_s=args.sim_time,
    )

    st["work"] = new_work

    write_json(d / "state.json", st)

    append_jsonl(d / "decisions.jsonl", {
        "sim_time_s": args.sim_time,
        "agent": args.callsign,
        "llm_ok": llm_result.get("ok"),
        "provider": llm_result.get("provider"),
        "model": llm_result.get("model"),
        "url": llm_result.get("url"),
        "http_status": llm_result.get("http_status"),
        "body_bytes": llm_result.get("body_bytes"),
        "ok": result.ok,
        "errors": result.errors,
        "raw_text": raw_text,
        "decision": result.decision,
    })
    append_jsonl(d / "tasks.jsonl", {
        "agent": args.callsign,
        "sim_time_s": int(args.sim_time),
        "work": new_work,
    })

    print("WROTE", d / "state.json")
    print("WROTE", d / "decisions.jsonl")
    print("WROTE", d / "tasks.jsonl")
    print("WROTE", outbox_path)
    print("WROTE", d / "last_system_prompt.txt")
    print("WROTE", d / "last_user_prompt.txt")
    print("WROTE", d / "last_full_prompt.txt")
    print("WROTE", d / "last_llm_response.txt")
    print("WROTE", d / "llm_trace.log")


if __name__ == "__main__":
    main()
