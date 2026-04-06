from __future__ import annotations

import argparse
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path
import sys

SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))
if str(SCRIPT_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT.parent))
from typing import Any, Dict, List

from llm_decision import build_agent_packet, parse_and_validate
from llm_runner import run_model
from prompting import write_prompt_log
from replay_paths import agent_dir, ensure_runtime_dirs
from state_store import (
    append_jsonl as store_append_jsonl,
    consume_transport_inbox,
    ensure_agent_layout as store_ensure_agent_layout,
    ensure_state_schema,
    load_state,
    message_token as store_message_token,
    move_new_messages_to_read,
    overwrite_jsonl as store_overwrite_jsonl,
    read_json as store_read_json,
    read_jsonl as store_read_jsonl,
    save_state,
    write_json as store_write_json,
)
from tasking import decision_to_work


def ensure_agent_layout(callsign: str) -> Path:
    return store_ensure_agent_layout(callsign)


def read_json(path: Path) -> Dict[str, Any]:
    return store_read_json(path, {})


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    store_write_json(path, obj)


def append_jsonl(path: Path, obj: Dict[str, Any]) -> None:
    store_append_jsonl(path, obj)


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    return store_read_jsonl(path)


def overwrite_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    store_overwrite_jsonl(path, rows)


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
    return ensure_state_schema(st)




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
        "constraints": {
            "roe": "defensive",
            "decision_horizon_sec": 300,
        },
        "work": [],
        "completed_work": [],
        "new_messages": [],
        "read_messages": [],
        "inbox": [],
        "seen_chat_uids": [],
        "private_referee": [],
        "pending_report_items": [],
        "world_changed_this_tick": False,
    }
    write_json(p, st)


def _msg_token(row: Dict[str, Any]) -> str:
    return store_message_token(row)


def ingest_inbox_into_state(callsign: str) -> Dict[str, Any]:
    d = ensure_agent_layout(callsign)
    state_path = d / "state.json"
    st = ensure_memory_fields(read_json(state_path))

    inbox_path = d / "inbox.jsonl"
    rows = read_jsonl(inbox_path)
    if inbox_path.exists():
        inbox_path.write_text("", encoding="utf-8")

    existing_new = list(st.get("new_messages") or [])
    existing_read = list(st.get("read_messages") or [])
    existing_seen = [str(x) for x in list(st.get("seen_chat_uids") or [])]
    seen = set(existing_seen)

    existing_new_tokens = {_msg_token(x) for x in existing_new if isinstance(x, dict)}
    existing_read_tokens = {_msg_token(x) for x in existing_read if isinstance(x, dict)}

    appended = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        tok = _msg_token(row)
        if tok in existing_new_tokens or tok in existing_read_tokens:
            continue
        msg = dict(row)
        msg["_message_token"] = tok
        appended.append(msg)
        if tok not in seen:
            existing_seen.append(tok)
            seen.add(tok)

    st["new_messages"] = (existing_new + appended)[-500:]
    st["inbox"] = list(st.get("new_messages") or [])
    st["seen_chat_uids"] = existing_seen[-2000:]
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
            "few obvious observation positions detected": "få tydliga spaningslägen identifierade",
            "open ground exposure": "öppen mark medför exponering",
            "road approach likely": "framryckning längs väg är sannolik",
            "foot infiltration via tracks/paths possible": "infiltration till fots via stigar och mindre vägar möjlig",
            "covered movement through built-up area possible": "skyddad framryckning genom bebyggelse möjlig",
            "concealed movement via tree cover possible": "dold framryckning via trädbevuxen terräng möjlig",
            "built-up edge positions": "läge i bebyggelsekant",
            "tree line / woodland edge": "läge i skogsbryn eller trädlinje",
            "waterfront observation line": "spaningslinje längs strand eller vatten",
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
            parts.append("Lämpliga spaningslägen: " + "; ".join(op[:2]))
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
    own = dict(st.get("own_state") or {})
    local_area = dict((st.get("geo") or {}).get("local_area") or {})

    subordinates = []
    for row in list(st.get("subordinates") or []):
        if not isinstance(row, dict):
            continue
        x = dict(row)
        x.pop("status", None)
        subordinates.append(x)

    packet = build_agent_packet(
        sim_time_s=int(sim_time_s),
        agent=agent,
        own_state=own,
        subordinates=subordinates,
        constraints=dict(st.get("constraints") or {}),
    )

    packet["geo"] = {
        "local_area_brief": _geo_area_brief(local_area, str(agent.get("language_profile") or "")),
    }

    packet["inbox"] = list(st.get("inbox") or [])
    packet["new_messages"] = list(st.get("new_messages") or [])
    packet["read_messages"] = list(st.get("read_messages") or [])[-3:]
    packet["completed_work"] = list(st.get("completed_work") or [])[-3:]

    trimmed_work = []
    for chain in list(st.get("work") or []):
        if not isinstance(chain, list) or not chain:
            continue
        trimmed_work.append([dict(x or {}) for x in chain[:2] if isinstance(x, dict)])
    packet["work"] = trimmed_work

    if packet.get("new_messages"):
        packet["inbox"] = []
    else:
        packet["inbox"] = list(packet.get("inbox") or [])[-3:]

    geo = dict(packet.get("geo") or {})
    brief = geo.get("local_area_brief")
    packet["geo"] = {"local_area_brief": brief} if brief else {}

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
    completed = list(st.get("completed_work") or [])
    item = dict(root or {})
    item.pop("status", None)
    if item.get("started_sim_time_s") is None:
        created = item.get("created_sim_time_s")
        item["started_sim_time_s"] = int(created if created is not None else sim_time_s)
    if item.get("deadline_sim_time_s") is None:
        item["deadline_sim_time_s"] = int(sim_time_s)
    item["completed_sim_time_s"] = int(sim_time_s)
    completed.append(item)
    st["completed_work"] = completed[-200:]

def _execute_move_unit(st: Dict[str, Any], root: Dict[str, Any], sim_time_s: int) -> None:
    params = dict(root.get("params") or {})
    own = st.setdefault("own_state", {})

    lat = params.get("lat", params.get("destination_lat"))
    lon = params.get("lon", params.get("destination_lon"))
    if lat is None or lon is None:
        return

    try:
        lat = float(lat)
        lon = float(lon)
    except Exception:
        return

    urgency = str(params.get("urgency") or params.get("movement_type") or "").strip()

    own["planned_movement"] = {
        "started_sim_time_s": int(sim_time_s),
        "destination": {
            "lat": lat,
            "lon": lon,
        },
        "urgency": urgency,
    }



def _progress_active_move_unit(st: Dict[str, Any], root: Dict[str, Any], sim_time_s: int) -> None:
    own = st.setdefault("own_state", {})
    pos = dict(own.get("position") or {})
    planned = dict(own.get("planned_movement") or {})
    params = dict(root.get("params") or {})

    started = root.get("started_sim_time_s")
    deadline = root.get("deadline_sim_time_s")
    if started is None or deadline is None:
        return

    try:
        started_i = int(started)
        deadline_i = int(deadline)
        now_i = int(sim_time_s)
        f_lat = float(pos.get("lat"))
        f_lon = float(pos.get("lon"))
    except Exception:
        return

    to_lat = params.get("lat", params.get("destination_lat"))
    to_lon = params.get("lon", params.get("destination_lon"))
    try:
        t_lat = float(to_lat)
        t_lon = float(to_lon)
    except Exception:
        return

    movement_from = dict(planned.get("from_position") or {})
    if movement_from:
        try:
            f_lat = float(movement_from.get("lat"))
            f_lon = float(movement_from.get("lon"))
        except Exception:
            pass
    else:
        planned["from_position"] = {"lat": f_lat, "lon": f_lon}

    total = max(1, deadline_i - started_i)
    elapsed = max(0, min(now_i - started_i, total))
    frac = elapsed / total

    own["position"] = {
        "lat": f_lat + (t_lat - f_lat) * frac,
        "lon": f_lon + (t_lon - f_lon) * frac,
    }

    planned["started_sim_time_s"] = started_i
    planned["destination"] = {"lat": t_lat, "lon": t_lon}
    planned["urgency"] = str(params.get("urgency") or params.get("movement_type") or "").strip()
    planned["progress"] = {
        "started_sim_time_s": started_i,
        "sim_time_s": now_i,
        "fraction": round(frac, 4),
    }
    own["planned_movement"] = planned


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
    # Intentionally no self-generated sightings.
    # World facts belong outside the unit; the unit must not invent them.
    return


def world_changed(st: Dict[str, Any], sim_time_s: int) -> bool:
    del sim_time_s
    return bool(st.get("world_changed_this_tick"))


def llm_trigger_reason(
    st: Dict[str, Any],
    callsign: str,
    sim_time_s: int,
    completed_before: int,
    completed_after: int,
) -> str:
    del callsign
    if list(st.get("new_messages") or []):
        return "new_messages"
    if completed_after > completed_before:
        return "deadline"
    if world_changed(st, sim_time_s):
        return "world_change"
    return ""



def _json_size_bytes(obj: Any) -> int:
    try:
        return len(json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    except Exception:
        return -1


def _message_token(row: Dict[str, Any]) -> str:
    return str(
        row.get("_message_token")
        or row.get("uid")
        or (
            f'{row.get("kind")}|{row.get("from")}|{row.get("to")}|'
            f'{row.get("sim_time_s")}|{row.get("message")}'
        )
    )


def _message_debug(st: Dict[str, Any]) -> Dict[str, Any]:
    names = ["inbox", "new_messages", "read_messages"]
    out: Dict[str, Any] = {"buckets": {}, "overlaps": {}}
    bucket_sets: Dict[str, set] = {}

    for name in names:
        rows = [dict(x or {}) for x in list(st.get(name) or []) if isinstance(x, dict)]
        toks = [_message_token(r) for r in rows]
        seen = set()
        dupes = []
        for t in toks:
            if t in seen and t not in dupes:
                dupes.append(t)
            seen.add(t)
        out["buckets"][name] = {
            "count": len(toks),
            "unique": len(set(toks)),
            "duplicate_count": len(toks) - len(set(toks)),
            "duplicate_samples": dupes[:5],
        }
        bucket_sets[name] = set(toks)

    for i, a in enumerate(names):
        for b in names[i+1:]:
            both = sorted(bucket_sets[a].intersection(bucket_sets[b]))
            out["overlaps"][f"{a}__{b}"] = {
                "count": len(both),
                "samples": both[:5],
            }

    return out


def _packet_part_sizes(packet: Dict[str, Any]) -> Dict[str, int]:
    keys = [
        "agent",
        "own_state",
        "subordinates",
        "constraints",
        "inbox",
        "new_messages",
        "read_messages",
        "work",
        "completed_work",
        "geo",
        "llm_trigger_reason",
    ]
    out: Dict[str, int] = {}
    for k in keys:
        if k in packet:
            out[k] = _json_size_bytes(packet.get(k))
    geo = packet.get("geo")
    if isinstance(geo, dict):
        if "local_area" in geo:
            out["geo.local_area"] = _json_size_bytes(geo.get("local_area"))
        if "local_area_brief" in geo:
            out["geo.local_area_brief"] = _json_size_bytes(geo.get("local_area_brief"))
    return out


def _decision_part_sizes(decision: Any) -> Dict[str, int]:
    if not isinstance(decision, dict):
        return {"decision": _json_size_bytes(decision)}
    out: Dict[str, int] = {"decision": _json_size_bytes(decision)}
    for k, v in decision.items():
        out[f"decision.{k}"] = _json_size_bytes(v)
    return out


def _print_llm_request_debug(packet: Dict[str, Any], st: Dict[str, Any], callsign: str) -> None:
    print(f"=== LLM REQUEST SIZE {callsign} ===")
    print(f"request.total_bytes={_json_size_bytes(packet)}")
    for k, v in sorted(_packet_part_sizes(packet).items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"request.part.{k}={v}")

    md = _message_debug(st)
    for bucket, info in md.get("buckets", {}).items():
        print(
            f"messages.{bucket}.count={info.get('count', 0)} "
            f"unique={info.get('unique', 0)} "
            f"duplicates={info.get('duplicate_count', 0)}"
        )
        samples = list(info.get("duplicate_samples") or [])
        for i, sample in enumerate(samples[:3], 1):
            print(f"messages.{bucket}.duplicate_sample_{i}={sample[:220]}")
    for pair, info in md.get("overlaps", {}).items():
        print(f"messages.overlap.{pair}={info.get('count', 0)}")
        samples = list(info.get("samples") or [])
        for i, sample in enumerate(samples[:3], 1):
            print(f"messages.overlap.{pair}.sample_{i}={sample[:220]}")


def _print_llm_response_debug(raw_text: str, result: Any, callsign: str) -> None:
    print(f"=== LLM RESPONSE SIZE {callsign} ===")
    print(f"response.raw_bytes={len((raw_text or '').encode('utf-8'))}")
    decision = getattr(result, "decision", None)
    for k, v in sorted(_decision_part_sizes(decision).items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"response.part.{k}={v}")
    errs = list(getattr(result, "errors", []) or [])
    print(f"response.errors.count={len(errs)}")
    if errs:
        for i, err in enumerate(errs[:5], 1):
            print(f"response.errors.{i}={str(err)[:300]}")
    print(f"response.ok={bool(getattr(result, 'ok', False))}")





def _strip_forbidden_state_shape(st: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(st, dict):
        return st

    st.pop("current_activity", None)
    st.pop("observations", None)

    work = []
    for chain in list(st.get("work") or []):
        if not isinstance(chain, list):
            continue
        out_chain = []
        for item in chain:
            if not isinstance(item, dict):
                continue
            x = dict(item)
            x.pop("status", None)
            out_chain.append(x)
        if out_chain:
            work.append(out_chain)
    st["work"] = work

    completed = []
    for item in list(st.get("completed_work") or []):
        if not isinstance(item, dict):
            continue
        x = dict(item)
        x.pop("status", None)
        completed.append(x)
    st["completed_work"] = completed

    return st

FORBIDDEN_TOPLEVEL_STATE_KEYS = {
    "current_activity",
    "observations",
}

FORBIDDEN_WORK_ITEM_KEYS = {
    "status",
}

def _assert_no_forbidden_state_shape(st: Dict[str, Any], where: str) -> None:
    bad_top = sorted(k for k in FORBIDDEN_TOPLEVEL_STATE_KEYS if k in st)
    if bad_top:
        raise RuntimeError(f"{where}: forbidden top-level state keys present: {bad_top}")

    work = list(st.get("work") or [])
    completed = list(st.get("completed_work") or [])

    def check_chain_items(items, bucket: str) -> None:
        for ci, chain in enumerate(items):
            if not isinstance(chain, list):
                continue
            for wi, item in enumerate(chain):
                if not isinstance(item, dict):
                    continue
                bad = sorted(k for k in FORBIDDEN_WORK_ITEM_KEYS if k in item)
                if bad:
                    raise RuntimeError(
                        f"{where}: forbidden work-item keys in {bucket}[{ci}][{wi}]: {bad}"
                    )

    check_chain_items(work, "work")

    # completed_work is a flat list, normalize to pseudo-chains for reuse
    for wi, item in enumerate(completed):
        if not isinstance(item, dict):
            continue
        bad = sorted(k for k in FORBIDDEN_WORK_ITEM_KEYS if k in item)
        if bad:
            raise RuntimeError(
                f"{where}: forbidden work-item keys in completed_work[{wi}]: {bad}"
            )



def _tick_active_runtime_action(st: Dict[str, Any], root: Dict[str, Any], sim_time_s: int) -> None:
    action = str(root.get("action") or "")
    own = st.setdefault("own_state", {})

    if action == "change_posture":
        params = dict(root.get("params") or {})
        posture = str(params.get("posture") or "").strip()
        if posture:
            own["posture"] = posture
        return

    if action == "hold_position":
        params = dict(root.get("params") or {})
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
        return

    if action != "move_unit":
        return

    params = dict(root.get("params") or {})
    lat = params.get("lat", params.get("destination_lat"))
    lon = params.get("lon", params.get("destination_lon"))
    if lat is None or lon is None:
        return

    try:
        dest_lat = float(lat)
        dest_lon = float(lon)
    except Exception:
        return

    pos = dict(own.get("position") or {})
    try:
        cur_lat = float(pos.get("lat"))
        cur_lon = float(pos.get("lon"))
    except Exception:
        return

    created = root.get("created_sim_time_s")
    started = root.get("started_sim_time_s")
    if started is None:
        started = int(created if created is not None else sim_time_s)
        root["started_sim_time_s"] = int(started)

    deadline = root.get("deadline_sim_time_s")
    if deadline is None:
        deadline = int(started) + int(root.get("duration_s") or 0)
        root["deadline_sim_time_s"] = int(deadline)

    try:
        started_i = int(started)
        deadline_i = int(deadline)
        now_i = int(sim_time_s)
    except Exception:
        return

    planned = dict(own.get("planned_movement") or {})
    origin = dict(planned.get("origin") or {})
    if not origin:
        origin = {"lat": cur_lat, "lon": cur_lon}
        planned["origin"] = origin

    planned["started_sim_time_s"] = started_i
    planned["destination"] = {"lat": dest_lat, "lon": dest_lon}
    planned["urgency"] = str(params.get("urgency") or params.get("movement_type") or "").strip()
    own["planned_movement"] = planned

    try:
        o_lat = float(origin.get("lat"))
        o_lon = float(origin.get("lon"))
    except Exception:
        o_lat = cur_lat
        o_lon = cur_lon

    total = max(1, deadline_i - started_i)
    elapsed = max(0, min(now_i - started_i, total))
    frac = elapsed / total

    own["position"] = {
        "lat": o_lat + (dest_lat - o_lat) * frac,
        "lon": o_lon + (dest_lon - o_lon) * frac,
    }
    own["planned_movement"]["progress"] = {
        "started_sim_time_s": started_i,
        "sim_time_s": now_i,
        "fraction": round(frac, 4),
    }


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
        created = root.get("created_sim_time_s")
        started = root.get("started_sim_time_s")
        if started is None:
            started = int(created if created is not None else sim_time_s)
            root["started_sim_time_s"] = int(started)

        deadline = root.get("deadline_sim_time_s")
        if deadline is None:
            deadline = int(started) + int(root.get("duration_s") or 0)
            root["deadline_sim_time_s"] = int(deadline)

        deadline_i = int(root.get("deadline_sim_time_s") or 0)

        _tick_active_runtime_action(st, root, sim_time_s)

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
            if deadline_i and int(sim_time_s) >= deadline_i:
                if action == "move_unit":
                    own = st.setdefault("own_state", {})
                    planned = dict(own.get("planned_movement") or {})
                    dest = dict(planned.get("destination") or {})
                    try:
                        lat = dest.get("lat")
                        lon = dest.get("lon")
                        if lat is not None and lon is not None:
                            own["position"] = {
                                "lat": float(lat),
                                "lon": float(lon),
                            }
                    except Exception:
                        pass
                    if "planned_movement" in own:
                        del own["planned_movement"]

                _complete_root(st, root, sim_time_s)
                completed_now = True

        if completed_now:
            if rest:
                nxt = dict(rest[0] or {})
                if nxt.get("created_sim_time_s") is None:
                    nxt["created_sim_time_s"] = int(sim_time_s)
                if nxt.get("started_sim_time_s") is not None:
                    nxt["started_sim_time_s"] = None
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

    st = ensure_memory_fields(ingest_inbox_into_state(args.callsign))
    st = _strip_forbidden_state_shape(st)
    _assert_no_forbidden_state_shape(st, "after_load")

    outbox_path = d / "outbox.jsonl"

    completed_before = len(list(st.get("completed_work") or []))

    # Kör roten på varje arbetskedja en gång per tick
    completed_after = process_work(st, args.sim_time, outbox_path)
    _assert_no_forbidden_state_shape(st, "after_process_work")

    trigger = llm_trigger_reason(
        st=st,
        callsign=args.callsign,
        sim_time_s=args.sim_time,
        completed_before=completed_before,
        completed_after=completed_after,
    )

    if not trigger:
        st["world_changed_this_tick"] = False
        _assert_no_forbidden_state_shape(st, "before_save_no_llm")
        save_state(args.callsign, st)
        return

    packet = build_packet_from_state(st, args.sim_time)
    packet["llm_trigger_reason"] = trigger

    # Slimma packet till LLM så prompten inte växer okontrollerat över tid.
    packet["new_messages"] = list(packet.get("new_messages") or [])
    packet["read_messages"] = list(packet.get("read_messages") or [])[-3:]
    packet["completed_work"] = list(packet.get("completed_work") or [])[-3:]

    slim_work = []
    for chain in list(packet.get("work") or []):
        if isinstance(chain, list) and chain:
            slim_work.append(chain[:2])
    packet["work"] = slim_work

    # inbox och new_messages överlappar i praktiken; låt new_messages vara sann källa.
    if packet.get("new_messages"):
        packet["inbox"] = []
    else:
        packet["inbox"] = list(packet.get("inbox") or [])[-3:]

    geo = dict(packet.get("geo") or {})
    if geo:
        brief = geo.get("local_area_brief")
        packet["geo"] = {"local_area_brief": brief} if brief else {}
    _print_llm_request_debug(packet, st, args.callsign)

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
    _print_llm_response_debug(raw_text, result, args.callsign)

    new_work = decision_to_work(
        decision=result.decision,
        sim_time_s=args.sim_time,
    )

    st["work"] = new_work

    # new_messages are consumed by a successful LLM cycle and moved to read_messages
    pending_messages = list(st.get("new_messages") or [])
    if pending_messages:
        read_hist = list(st.get("read_messages") or [])
        read_hist.extend(pending_messages)
        st["read_messages"] = read_hist[-500:]
        st["new_messages"] = []
        st["inbox"] = []

    st["world_changed_this_tick"] = False
    _assert_no_forbidden_state_shape(st, "before_save_after_llm")
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
