from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from llm_decision import build_agent_packet, parse_and_validate
from llm_runner import run_model
from prompting import write_prompt_log
from replay_paths import agent_dir, ensure_runtime_dirs
from tasking import decision_to_work

ALLOWED_TIMED_WORK = {"planning", "execute_action"}


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
    st.setdefault("friendly_reports", [])
    st.setdefault("observations", [])
    st.setdefault("private_referee", {})
    st.setdefault("last_order", None)
    st.setdefault("atak_view", [])
    st.setdefault("work", [])
    st.setdefault("completed_work", [])
    st.setdefault("idle_since_sim_time_s", 0)

    st.setdefault("control", {})
    ctl = st["control"]
    if not isinstance(ctl, dict):
        ctl = {}
        st["control"] = ctl
    ctl.setdefault("next_decision_due_sim_time_s", 0)

    st.setdefault("memory", {})
    mem = st["memory"]
    if not isinstance(mem, dict):
        mem = {}
        st["memory"] = mem

    mem.setdefault("received_orders", [])
    mem.setdefault("sent_orders", [])
    mem.setdefault("received_reports", [])
    mem.setdefault("sent_reports", [])
    mem.setdefault("open_issues", [])
    mem.setdefault("awaiting_response_from", [])
    mem.setdefault("current_intent", "")
    mem.setdefault("current_plan", "")
    return st


def remember_received_order(st: Dict[str, Any], sender: str, sim_time_s: int, text: str, meta: Dict[str, Any]) -> None:
    st = ensure_memory_fields(st)
    row = {
        "from": sender,
        "sim_time_s": int(sim_time_s),
        "message": text,
        "meta": meta or {},
    }
    st["memory"]["received_orders"] = tail_list(list(st["memory"]["received_orders"]) + [row], 20)


def remember_sent_order(st: Dict[str, Any], recipient: str, sim_time_s: int, text: str, meta: Dict[str, Any]) -> None:
    st = ensure_memory_fields(st)
    row = {
        "to": recipient,
        "sim_time_s": int(sim_time_s),
        "message": text,
        "meta": meta or {},
    }
    st["memory"]["sent_orders"] = tail_list(list(st["memory"]["sent_orders"]) + [row], 40)

    awaiting = [str(x) for x in list(st["memory"].get("awaiting_response_from") or [])]
    if recipient and recipient not in awaiting:
        awaiting.append(recipient)
    st["memory"]["awaiting_response_from"] = awaiting[-40:]


def remember_received_report(st: Dict[str, Any], sender: str, sim_time_s: int, text: str, kind: str, meta: Dict[str, Any]) -> None:
    st = ensure_memory_fields(st)
    row = {
        "from": sender,
        "sim_time_s": int(sim_time_s),
        "kind": kind,
        "message": text,
        "meta": meta or {},
    }
    st["memory"]["received_reports"] = tail_list(list(st["memory"]["received_reports"]) + [row], 40)

    awaiting = [str(x) for x in list(st["memory"].get("awaiting_response_from") or [])]
    awaiting = [x for x in awaiting if x != sender]
    st["memory"]["awaiting_response_from"] = awaiting[-40:]


def remember_sent_report(st: Dict[str, Any], recipient: str, sim_time_s: int, text: str, kind: str, meta: Dict[str, Any]) -> None:
    st = ensure_memory_fields(st)
    row = {
        "to": recipient,
        "sim_time_s": int(sim_time_s),
        "kind": kind,
        "message": text,
        "meta": meta or {},
    }
    st["memory"]["sent_reports"] = tail_list(list(st["memory"]["sent_reports"]) + [row], 40)


def rebuild_open_issues(st: Dict[str, Any]) -> None:
    st = ensure_memory_fields(st)

    issues: List[str] = []
    awaiting = [str(x) for x in list(st["memory"].get("awaiting_response_from") or []) if str(x).strip()]
    if awaiting:
        issues.append("Inväntar återrapport från: " + ", ".join(awaiting))

    for rep in list(st.get("friendly_reports") or [])[-10:]:
        kind = str(rep.get("kind") or "")
        sender = str(rep.get("from") or "")
        meta = dict(rep.get("meta") or {})
        text = str(rep.get("text") or "")

        if kind == "support_request":
            issues.append(f"{sender} begär stöd")
        elif kind == "casualty_report":
            wounded = meta.get("wounded")
            killed = meta.get("killed")
            issues.append(f"{sender} rapporterar förluster sårade={wounded} stupade={killed}")
        elif kind == "contact_report":
            desc = str(meta.get("description") or text or "fiendekontakt")
            issues.append(f"{sender} rapporterar kontakt: {desc}")

    dedup: List[str] = []
    seen = set()
    for x in issues:
        if x not in seen:
            dedup.append(x)
            seen.add(x)

    st["memory"]["open_issues"] = dedup[-20:]


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
        "friendly_reports": [],
        "observations": [],
        "constraints": {
            "roe": "defensive",
            "decision_horizon_sec": 300,
        },
        "last_order": None,
        "private_referee": {},
        "atak_view": [],
        "work": [],
        "completed_work": [],
        "idle_since_sim_time_s": 0,
        "control": {
            "decision_policy": "on_change",
            "decision_horizon_source": "global",
            "status_interval_sec": 1800,
            "run_if_idle": False,
            "next_decision_due_sim_time_s": 0,
        },
        "memory": {
            "received_orders": [],
            "sent_orders": [],
            "received_reports": [],
            "sent_reports": [],
            "open_issues": [],
            "awaiting_response_from": [],
            "current_intent": "",
            "current_plan": "",
        },
    }
    write_json(p, st)


def ingest_inbox_into_state(callsign: str) -> Dict[str, Any]:
    d = ensure_agent_layout(callsign)
    state_path = d / "state.json"
    inbox_path = d / "inbox.jsonl"

    st = ensure_memory_fields(read_json(state_path))
    inbox = read_jsonl(inbox_path)
    if not inbox:
        rebuild_open_issues(st)
        write_json(state_path, st)
        return st

    # Enkel modell: om enheten redan arbetar, lämnas inkommande meddelanden i inboxen
    if has_work(st):
        rebuild_open_issues(st)
        write_json(state_path, st)
        return st

    remaining = list(inbox)
    msg = remaining.pop(0)

    kind = str(msg.get("kind") or "")
    sender = str(msg.get("from") or "")
    meta = msg.get("meta") or {}
    text = str(msg.get("message") or "")
    sim_time_s = int(msg.get("sim_time_s") or 0)

    if kind == "order":
        st["last_order"] = {
            "from": sender,
            "sim_time_s": sim_time_s,
            "message": text,
            "meta": meta,
        }
        remember_received_order(st, sender, sim_time_s, text, meta)

    elif kind in {"contact_report", "casualty_report", "support_request", "status_report"}:
        reps = list(st.get("friendly_reports") or [])
        reps.append({
            "from": sender,
            "age_sec": 0,
            "text": text,
            "kind": kind,
            "meta": meta,
            "sim_time_s": sim_time_s,
        })
        st["friendly_reports"] = reps[-50:]
        remember_received_report(st, sender, sim_time_s, text, kind, meta)

    else:
        remaining.insert(0, msg)

    overwrite_jsonl(inbox_path, remaining)
    rebuild_open_issues(st)
    write_json(state_path, st)
    return st


def build_atak_view(st: Dict[str, Any]) -> List[Dict[str, Any]]:
    view: List[Dict[str, Any]] = []
    for sub in list(st.get("subordinates") or []):
        callsign = str(sub.get("callsign") or "").strip()
        if not callsign:
            continue

        sub_state_path = agent_dir(callsign) / "state.json"
        sub_state = read_json(sub_state_path)
        if not sub_state:
            view.append({
                "callsign": callsign,
                "status": str(sub.get("status") or "unknown"),
                "known": False,
            })
            continue

        own = dict(sub_state.get("own_state") or {})
        agent = dict(sub_state.get("agent") or {})
        last_order = dict(sub_state.get("last_order") or {})

        current_action = None
        work = list(sub_state.get("work") or [])
        for chain in work:
            if isinstance(chain, list) and chain:
                root = chain[0]
                if str(root.get("kind") or "") == "execute_action":
                    current_action = root.get("action")
                    break

        row = {
            "callsign": callsign,
            "known": True,
            "role": agent.get("role"),
            "control_mode": agent.get("control_mode"),
            "position": own.get("position"),
            "posture": own.get("posture"),
            "readiness": own.get("readiness"),
            "combat_value": own.get("combat_value"),
            "strength": own.get("strength"),
            "current_action": current_action,
            "last_order_from": last_order.get("from"),
            "last_order_sim_time_s": last_order.get("sim_time_s"),
        }
        view.append(row)
    return view


def build_packet_from_state(st: Dict[str, Any], sim_time_s: int) -> Dict[str, Any]:
    packet = build_agent_packet(
        sim_time_s=sim_time_s,
        agent=dict(st.get("agent") or {}),
        own_state=dict(st.get("own_state") or {}),
        subordinates=list(st.get("subordinates") or []),
        observations=list(st.get("observations") or []),
        friendly_reports=list(st.get("friendly_reports") or []),
        constraints=dict(st.get("constraints") or {}),
        last_order=st.get("last_order"),
    )

    mem = dict(st.get("memory") or {})
    packet["atak_view"] = list(st.get("atak_view") or [])
    packet["work"] = list(st.get("work") or [])
    packet["completed_work"] = list(st.get("completed_work") or [])
    packet["memory_summary"] = {
        "received_orders": tail_list(list(mem.get("received_orders") or []), 10),
        "sent_orders": tail_list(list(mem.get("sent_orders") or []), 10),
        "received_reports": tail_list(list(mem.get("received_reports") or []), 15),
        "sent_reports": tail_list(list(mem.get("sent_reports") or []), 10),
        "open_issues": list(mem.get("open_issues") or []),
        "awaiting_response_from": list(mem.get("awaiting_response_from") or []),
        "current_intent": str(mem.get("current_intent") or ""),
        "current_plan": str(mem.get("current_plan") or ""),
    }
    return packet


def load_model_response(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def append_completed_work(st: Dict[str, Any], item: Dict[str, Any]) -> None:
    completed = list(st.get("completed_work") or [])
    completed.append(item)
    st["completed_work"] = completed[-200:]


def emit_order_to_subordinates(
    callsign: str,
    item: Dict[str, Any],
    sim_time_s: int,
    outbox_path: Path,
    st: Dict[str, Any],
) -> None:
    subs = list(st.get("subordinates") or [])
    if not subs:
        return

    message = str(item.get("message") or "").strip()
    if not message:
        return

    for sub in subs:
        sub_cs = str(sub.get("callsign") or "").strip()
        if not sub_cs:
            continue

        meta = {
            "action": item.get("action"),
            "target": item.get("target"),
            "formation": item.get("formation"),
            "tempo": item.get("tempo"),
            "engagement": item.get("engagement"),
            "intent": item.get("intent"),
            "confidence": item.get("confidence"),
        }

        msg = {
            "kind": "order",
            "from": callsign,
            "to": sub_cs,
            "sim_time_s": int(sim_time_s),
            "message": message,
            "meta": meta,
        }
        append_jsonl(outbox_path, msg)
        remember_sent_order(st, sub_cs, sim_time_s, message, meta)


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
    remember_sent_report(st, superior, sim_time_s, message, "status_report", meta)


def process_work(st: Dict[str, Any], sim_time_s: int, outbox_path: Path) -> None:
    callsign = str((st.get("agent") or {}).get("callsign") or "")
    superior = str((st.get("agent") or {}).get("superior") or "")

    new_work: List[List[Dict[str, Any]]] = []
    for chain in list(st.get("work") or []):
        if not isinstance(chain, list) or not chain:
            continue

        root = dict(chain[0] or {})
        kind = str(root.get("kind") or "")
        status = str(root.get("status") or "")
        deadline = int(root.get("deadline_sim_time_s") or 0)

        keep_chain = True

        if kind == "send_order":
            emit_order_to_subordinates(callsign, root, sim_time_s, outbox_path, st)
            root["status"] = "completed"
            root["completed_sim_time_s"] = int(sim_time_s)
            append_completed_work(st, root)
            keep_chain = False

        elif kind == "send_report":
            emit_report_up(callsign, superior, root, sim_time_s, outbox_path, st)
            root["status"] = "completed"
            root["completed_sim_time_s"] = int(sim_time_s)
            append_completed_work(st, root)
            keep_chain = False

        elif kind in ALLOWED_TIMED_WORK:
            if status == "active" and deadline and int(sim_time_s) >= deadline:
                root["status"] = "completed"
                root["completed_sim_time_s"] = int(sim_time_s)
                append_completed_work(st, root)
                keep_chain = False

        if keep_chain:
            new_work.append(chain)

    st["work"] = new_work


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

    # Kör roten på varje arbetskedja en gång per tick
    process_work(st, args.sim_time, outbox_path)

    # Om det fortfarande finns arbete kvar efter ticken, skriv state och avsluta
    if has_work(st):
        st["atak_view"] = build_atak_view(st)
        rebuild_open_issues(st)
        write_json(d / "state.json", st)
        return

    st["atak_view"] = build_atak_view(st)
    packet = build_packet_from_state(st, args.sim_time)

    if args.live_llm:
        llm_result = run_model(
            packet=packet,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            seed=args.seed,
        )
        raw_text = llm_result.get("text") or ""
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

    decision_horizon_s = int((st.get("constraints") or {}).get("decision_horizon_sec") or 300)
    has_subordinates = bool(list(st.get("subordinates") or []))
    superior_callsign = str((st.get("agent") or {}).get("superior") or "")

    new_work = decision_to_work(
        agent_callsign=args.callsign,
        superior_callsign=superior_callsign,
        decision=result.decision,
        sim_time_s=args.sim_time,
        has_subordinates=has_subordinates,
        decision_horizon_s=decision_horizon_s,
    )

    st["work"] = list(st.get("work") or []) + new_work

    st["memory"]["current_intent"] = str(result.decision.get("intent") or "")
    current_plan_bits: List[str] = []
    if result.decision.get("action"):
        current_plan_bits.append(f"action={result.decision.get('action')}")
    if result.decision.get("target"):
        current_plan_bits.append(f"target={result.decision.get('target')}")
    if result.decision.get("formation"):
        current_plan_bits.append(f"formation={result.decision.get('formation')}")
    if result.decision.get("tempo"):
        current_plan_bits.append(f"tempo={result.decision.get('tempo')}")
    st["memory"]["current_plan"] = ", ".join(current_plan_bits)

    if not has_work(st):
        st["idle_since_sim_time_s"] = int(args.sim_time)

    rebuild_open_issues(st)
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
