from __future__ import annotations

import argparse
import json
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





def _geo_area_summary_for_state(st: Dict[str, Any]) -> Dict[str, Any]:


def _geo_area_brief(local_area: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(local_area, dict) or not local_area.get("ok"):
        return {
            "ok": False,
            "summary_sv": "Ingen geografisk områdessammanfattning tillgänglig.",
        }

    mobility = dict(local_area.get("mobility") or {})
    ta = dict(local_area.get("tactical_assessment") or {})

    named = list(local_area.get("named_pois") or [])
    likely = list(ta.get("likely_approach_routes") or [])
    op = list(ta.get("good_op_positions") or [])
    risks = list(ta.get("risk_areas") or [])

    parts = []
    if named:
        parts.append("Viktiga terrängföremål: " + ", ".join(named[:3]))
    if mobility:
        parts.append(
            "Framkomlighet: fot="
            + str(mobility.get("foot") or "okänd")
            + ", fordon="
            + str(mobility.get("vehicle") or "okänd")
            + ", skydd="
            + str(mobility.get("concealment") or "okänd")
            + ", observation="
            + str(mobility.get("observation") or "okänd")
        )
    if likely:
        parts.append("Sannolika framryckningsvägar: " + "; ".join(likely[:2]))
    if op:
        parts.append("Lämpliga observationslägen: " + "; ".join(op[:2]))
    if risks:
        parts.append("Riskytor: " + "; ".join(risks[:2]))

    return {
        "ok": True,
        "named_features": named[:6],
        "mobility": mobility,
        "likely_approach_routes": likely[:4],
        "good_op_positions": op[:4],
        "risk_areas": risks[:4],
        "summary_sv": " | ".join(parts) if parts else "Ingen tydlig terrängbedömning tillgänglig.",
    }

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
        with urllib.request.urlopen(url, timeout=8.0) as r:
            raw = (r.read() or b"").decode("utf-8", "replace")
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
        return {"ok": False, "error": "invalid_geo_payload"}
    except Exception as e:
        return {"ok": False, "error": f"geo_lookup_failed: {e}"}


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
        "local_area_brief": _geo_area_brief(local_area),
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

        root = dict(chain[0] or {})
        action = str(root.get("action") or "")
        status = str(root.get("status") or "")
        deadline = int(root.get("deadline_sim_time_s") or 0)

        keep_chain = True

        if action == "send_message":
            emit_message_action(callsign, root, sim_time_s, outbox_path, st)
            root["status"] = "completed"
            root["completed_sim_time_s"] = int(sim_time_s)
            append_completed_work(st, root)
            keep_chain = False

        elif action == "report_status":
            params = dict(root.get("params") or {})
            recipient = str(params.get("recipient") or superior).strip()
            root["message"] = str(params.get("message") or "")
            emit_report_up(callsign, recipient, root, sim_time_s, outbox_path, st)
            root["status"] = "completed"
            root["completed_sim_time_s"] = int(sim_time_s)
            append_completed_work(st, root)
            keep_chain = False

        elif action in {
            "llm_replan_from_inbox",
            "llm_replan_from_deadline",
            "llm_replan_from_world_change",
            "move_unit",
            "change_posture",
            "observe_area",
            "hold_position",
        }:
            if status == "active" and deadline and int(sim_time_s) >= deadline:
                root["status"] = "completed"
                root["completed_sim_time_s"] = int(sim_time_s)
                append_completed_work(st, root)
                keep_chain = False

        if keep_chain:
            new_work.append(chain)

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
