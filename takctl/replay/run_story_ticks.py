from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

from replay_paths import SOURCE_ROOT, STATE_ROOT

RUN_TICK = SOURCE_ROOT / "run_sim_tick.py"


def _run_tick(sim_time_s: int) -> Tuple[int, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = "/opt/tak/tools/takctl"
    proc = subprocess.run(
        [sys.executable, str(RUN_TICK), "--sim-time", str(sim_time_s)],
        capture_output=True,
        text=True,
        env=env,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, out


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        txt = path.read_text(encoding="utf-8").strip()
        return json.loads(txt) if txt else {}
    except Exception:
        return {}


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            out.append(json.loads(line))
    except Exception:
        return out
    return out


def _target_to_str(target: Any) -> str:
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
        return "point"
    return ""


def _root_work_items(st: Dict[str, Any]) -> List[Dict[str, Any]]:
    roots: List[Dict[str, Any]] = []
    for chain in list(st.get("work") or []):
        if isinstance(chain, list) and chain:
            root = chain[0]
            if isinstance(root, dict):
                roots.append(root)
    return roots


def _first_execute_action(roots: List[Dict[str, Any]]) -> Dict[str, Any]:
    for root in roots:
        if str(root.get("kind") or "") == "execute_action":
            return root
    return {}


def _first_planning(roots: List[Dict[str, Any]]) -> Dict[str, Any]:
    for root in roots:
        if str(root.get("kind") or "") == "planning":
            return root
    return {}


def _pending_kind_count(roots: List[Dict[str, Any]], kind: str) -> int:
    n = 0
    for root in roots:
        if str(root.get("kind") or "") == kind:
            n += 1
    return n


def _unit_status(callsign: str) -> Dict[str, Any]:
    d = STATE_ROOT / "agents" / callsign
    st = _read_json(d / "state.json")
    inbox = _read_jsonl(d / "inbox.jsonl")
    outbox = _read_jsonl(d / "outbox.jsonl")

    roots = _root_work_items(st)
    execute = _first_execute_action(roots)
    planning = _first_planning(roots)
    completed_work = list(st.get("completed_work") or [])

    if roots:
        mode = "WORKING"
    elif inbox:
        mode = "IDLE inbox>0"
    else:
        mode = "IDLE inbox=0"

    sent_orders = 0
    sent_reports = 0
    for row in outbox[-20:]:
        kind = str(row.get("kind") or "")
        if kind == "order":
            sent_orders += 1
        elif kind.endswith("report") or kind == "status_report":
            sent_reports += 1

    return {
        "callsign": callsign,
        "mode": mode,
        "inbox_count": len(inbox),
        "root_kinds": [str(x.get("kind") or "") for x in roots],
        "execute_action": str(execute.get("action") or ""),
        "execute_target": _target_to_str(execute.get("target")),
        "execute_deadline": execute.get("deadline_sim_time_s"),
        "planning_deadline": planning.get("deadline_sim_time_s"),
        "planning_reason": str(planning.get("reason") or ""),
        "pending_send_orders": _pending_kind_count(roots, "send_order"),
        "pending_send_reports": _pending_kind_count(roots, "send_report"),
        "completed_count": len(completed_work),
        "sent_orders_recent": sent_orders,
        "sent_reports_recent": sent_reports,
    }


def _storyline(sim_time_s: int, units: List[Dict[str, Any]]) -> List[str]:
    lines: List[str] = []

    working = [u for u in units if u["mode"] == "WORKING"]
    inbox_wait = [u for u in units if u["mode"] == "IDLE inbox>0"]
    idle = [u for u in units if u["mode"] == "IDLE inbox=0"]

    parts: List[str] = []
    if working:
        parts.append(f"WORKING {len(working)}")
    if inbox_wait:
        parts.append(f"IDLE inbox>0 {len(inbox_wait)}")
    if idle:
        parts.append(f"IDLE inbox=0 {len(idle)}")

    lines.append(f"T{sim_time_s}: " + ", ".join(parts))

    important: List[str] = []
    for u in units:
        cs = u["callsign"]

        if u["mode"] == "WORKING":
            desc = f"{cs} arbetar"
            if u["root_kinds"]:
                desc += f" med {', '.join(u['root_kinds'])}"
            if u["execute_action"]:
                desc += f"; uppgift {u['execute_action']}"
            if u["execute_target"]:
                desc += f" mot {u['execute_target']}"
            if u["execute_deadline"] is not None:
                desc += f"; exec till {u['execute_deadline']}"
            if u["planning_deadline"] is not None:
                desc += f"; plan till {u['planning_deadline']}"
            important.append(desc)

        elif u["mode"] == "IDLE inbox>0":
            important.append(f"{cs} väntar med {u['inbox_count']} i inkorg")

        if u["pending_send_orders"] > 0:
            important.append(f"{cs} har {u['pending_send_orders']} väntande send_order")
        if u["pending_send_reports"] > 0:
            important.append(f"{cs} har {u['pending_send_reports']} väntande send_report")
        if u["sent_orders_recent"] > 0:
            important.append(f"{cs} har {u['sent_orders_recent']} order i recent outbox")
        if u["sent_reports_recent"] > 0:
            important.append(f"{cs} har {u['sent_reports_recent']} rapporter i recent outbox")

    seen = set()
    deduped: List[str] = []
    for x in important:
        if x not in seen:
            deduped.append(x)
            seen.add(x)

    lines.extend("  - " + x for x in deduped[:12])
    return lines


def _brief_line(u: Dict[str, Any]) -> str:
    bits = [u["callsign"], u["mode"]]
    if u["inbox_count"]:
        bits.append(f"inbox={u['inbox_count']}")
    if u["root_kinds"]:
        bits.append(f"roots={','.join(u['root_kinds'])}")
    if u["execute_action"]:
        bits.append(f"task={u['execute_action']}")
    if u["execute_target"]:
        bits.append(f"target={u['execute_target']}")
    if u["execute_deadline"] is not None:
        bits.append(f"exec_deadline={u['execute_deadline']}")
    if u["planning_deadline"] is not None:
        bits.append(f"plan_deadline={u['planning_deadline']}")
    if u["pending_send_orders"]:
        bits.append(f"send_order={u['pending_send_orders']}")
    if u["pending_send_reports"]:
        bits.append(f"send_report={u['pending_send_reports']}")
    if u["completed_count"]:
        bits.append(f"completed={u['completed_count']}")
    return " ".join(str(x) for x in bits if x not in ("", None))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--times", nargs="+", type=int, required=True)
    ap.add_argument("--agents", nargs="*", default=["VQ", "PQ", "QQ", "RQ", "SQ", "TQ", "AQ"])
    ap.add_argument("--show-raw-on-error", action="store_true")
    args = ap.parse_args()

    for sim_time_s in args.times:
        rc, raw = _run_tick(sim_time_s)
        units = [_unit_status(cs) for cs in args.agents]

        print(f"=== TICK {sim_time_s} rc={rc} ===")
        for line in _storyline(sim_time_s, units):
            print(line)

        print("  state:")
        for u in units:
            print("   -", _brief_line(u))

        if rc != 0 and args.show_raw_on_error:
            print()
            print("RAW:")
            print(raw.rstrip())
        print()


if __name__ == "__main__":
    main()
