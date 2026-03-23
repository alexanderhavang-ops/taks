from __future__ import annotations

from typing import Any, Dict, List, Optional


ALLOWED_ACTIONS = {
    "move",
    "observe",
    "reposition",
    "withdraw",
    "hold",
    "assault",
    "support_by_fire",
}


def normalize_target(target: Any) -> Optional[Dict[str, Any]]:
    if target is None:
        return None
    if not isinstance(target, dict):
        return None

    ttype = str(target.get("type") or "")

    if ttype == "point":
        return {
            "type": "point",
            "lat": target.get("lat"),
            "lon": target.get("lon"),
        }

    if ttype == "unit":
        return {
            "type": "unit",
            "callsign": target.get("callsign"),
        }

    if ttype == "area":
        return {
            "type": "area",
            "name": target.get("name"),
        }

    return None


def normalize_action(agent_callsign: str, action: Any) -> str:
    a = str(action or "hold")

    # PQ är stabselement och kvarstannar normalt.
    if str(agent_callsign).upper() == "PQ" and a == "move":
        return "hold"

    if a not in ALLOWED_ACTIONS:
        return "hold"
    return a


def decision_to_work(
    agent_callsign: str,
    superior_callsign: str,
    decision: Dict[str, Any],
    sim_time_s: int,
    has_subordinates: bool,
    decision_horizon_s: int,
) -> List[List[Dict[str, Any]]]:
    action = normalize_action(agent_callsign, decision.get("action"))
    target = normalize_target(decision.get("target"))
    formation = str(decision.get("formation") or "defensive")
    tempo = str(decision.get("tempo") or "static")
    engagement = str(decision.get("engagement") or "return_fire_only")
    report_up = str(decision.get("report_up") or "").strip()
    order_text = str(decision.get("order_text") or "").strip()
    intent = str(decision.get("intent") or "").strip()
    confidence = float(decision.get("confidence") or 0.0)

    planning_in = dict(decision.get("planning") or {})
    needs_planning = bool(planning_in.get("needs_planning", False))
    planning_time_s = int(planning_in.get("planning_time_s") or 0)
    planning_reason = str(planning_in.get("reason") or "").strip()

    work: List[List[Dict[str, Any]]] = []

    if report_up and superior_callsign:
        work.append([
            {
                "kind": "send_report",
                "status": "pending",
                "created_sim_time_s": int(sim_time_s),
                "to": superior_callsign,
                "message": report_up,
                "meta": {
                    "confidence": confidence,
                },
            }
        ])

    if order_text and has_subordinates:
        work.append([
            {
                "kind": "send_order",
                "status": "pending",
                "created_sim_time_s": int(sim_time_s),
                "message": order_text,
                "intent": intent,
                "action": action,
                "target": target,
                "formation": formation,
                "tempo": tempo,
                "engagement": engagement,
                "confidence": confidence,
            }
        ])

    if needs_planning:
        work.append([
            {
                "kind": "planning",
                "status": "active",
                "created_sim_time_s": int(sim_time_s),
                "started_sim_time_s": int(sim_time_s),
                "deadline_sim_time_s": int(sim_time_s) + max(0, planning_time_s),
                "reason": planning_reason,
                "intent": intent,
                "action": action,
                "target": target,
                "formation": formation,
                "tempo": tempo,
                "engagement": engagement,
                "confidence": confidence,
            }
        ])

    if action in ALLOWED_ACTIONS:
        work.append([
            {
                "kind": "execute_action",
                "status": "active",
                "created_sim_time_s": int(sim_time_s),
                "started_sim_time_s": int(sim_time_s),
                "deadline_sim_time_s": int(sim_time_s) + max(0, decision_horizon_s),
                "intent": intent,
                "action": action,
                "target": target,
                "formation": formation,
                "tempo": tempo,
                "engagement": engagement,
                "confidence": confidence,
            }
        ])

    return work


if __name__ == "__main__":
    decision = {
        "intent": "försvara Ystads hamn",
        "action": "move",
        "target": {"type": "area", "name": "Ystad harbor east"},
        "formation": "column",
        "tempo": "urgent",
        "engagement": "return_fire_only",
        "report_up": "VQ rapporterar mottagen order och påbörjade åtgärder.",
        "order_text": "Varningsorder till underlydande: höj stridsberedskap och förbered rörelse.",
        "confidence": 0.82,
        "planning": {
            "needs_planning": True,
            "planning_time_s": 240,
            "reason": "Kort planering krävs för samordning.",
        },
    }

    work = decision_to_work(
        agent_callsign="VQ",
        superior_callsign="MR S",
        decision=decision,
        sim_time_s=0,
        has_subordinates=True,
        decision_horizon_s=300,
    )

    import json
    print(json.dumps(work, ensure_ascii=False, indent=2))
