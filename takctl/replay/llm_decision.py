from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

ALLOWED_ACTIONS = {
    "hold",
    "move",
    "observe",
    "withdraw",
    "assault",
    "support_by_fire",
    "reposition",
    "report_only",
}

ALLOWED_FORMATIONS = {
    "defensive",
    "dispersed",
    "column",
    "bounding",
    "line",
    "wedge",
    "static",
}

ALLOWED_TEMPO = {
    "static",
    "cautious",
    "deliberate",
    "urgent",
}

ALLOWED_ENGAGEMENT = {
    "hold_fire",
    "return_fire_only",
    "engage_if_in_range",
    "fire_and_maneuver",
    "smoke_and_break_contact",
}


@dataclass
class DecisionResult:
    ok: bool
    decision: Dict[str, Any]
    errors: List[str]
    raw_text: str


def build_agent_packet(
    *,
    sim_time_s: int,
    agent: Dict[str, Any],
    own_state: Dict[str, Any],
    subordinates: List[Dict[str, Any]],
    observations: List[Dict[str, Any]],
    friendly_reports: List[Dict[str, Any]],
    constraints: Dict[str, Any],
    last_order: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    packet: Dict[str, Any] = {
        "sim_time_s": int(sim_time_s),
        "agent": agent,
        "own_state": own_state,
        "subordinates": subordinates,
        "observations": observations,
        "friendly_reports": friendly_reports,
        "constraints": constraints,
    }

    if last_order is not None:
        packet["last_order"] = last_order

    return packet


def parse_llm_json(raw_text: str) -> Dict[str, Any]:
    s = raw_text.strip()

    if s.startswith("```"):
        lines = s.splitlines()
        if len(lines) >= 3:
            s = "\n".join(lines[1:-1]).strip()

    return json.loads(s)


def validate_decision(d: Dict[str, Any]) -> List[str]:
    errors: List[str] = []

    required = [
        "intent",
        "action",
        "target",
        "formation",
        "tempo",
        "engagement",
        "report_up",
        "order_text",
        "planning",
        "confidence",
    ]

    for k in required:
        if k not in d:
            errors.append(f"missing field: {k}")

    if errors:
        return errors

    if not isinstance(d["intent"], str) or not d["intent"].strip():
        errors.append("intent must be non-empty string")

    if d["action"] not in ALLOWED_ACTIONS:
        errors.append(f"invalid action: {d['action']}")

    if d["formation"] not in ALLOWED_FORMATIONS:
        errors.append(f"invalid formation: {d['formation']}")

    if d["tempo"] not in ALLOWED_TEMPO:
        errors.append(f"invalid tempo: {d['tempo']}")

    if d["engagement"] not in ALLOWED_ENGAGEMENT:
        errors.append(f"invalid engagement: {d['engagement']}")

    conf = d["confidence"]
    if not isinstance(conf, (int, float)) or conf < 0 or conf > 1:
        errors.append("confidence must be between 0 and 1")

    report_up = d["report_up"]
    if not isinstance(report_up, str) or not report_up.strip():
        errors.append("report_up must be non-empty string")

    order_text = d["order_text"]
    if not isinstance(order_text, str):
        errors.append("order_text must be string")

    planning = d["planning"]
    if not isinstance(planning, dict):
        errors.append("planning must be object")
    else:
        if "needs_planning" not in planning:
            errors.append("planning.needs_planning missing")
        elif not isinstance(planning["needs_planning"], bool):
            errors.append("planning.needs_planning must be bool")

        if "planning_time_s" not in planning:
            errors.append("planning.planning_time_s missing")
        else:
            pts = planning["planning_time_s"]
            if not isinstance(pts, int) or pts < 0:
                errors.append("planning.planning_time_s must be int >= 0")

        if "reason" not in planning:
            errors.append("planning.reason missing")
        elif not isinstance(planning["reason"], str):
            errors.append("planning.reason must be string")

    target = d["target"]

    if target is not None:
        if not isinstance(target, dict):
            errors.append("target must be null or object")
        else:
            ttype = target.get("type")

            if ttype not in {"point", "unit", "area"}:
                errors.append("invalid target.type")

            elif ttype == "point":
                if "lat" not in target or "lon" not in target:
                    errors.append("point target requires lat/lon")

            elif ttype == "unit":
                if "callsign" not in target:
                    errors.append("unit target requires callsign")

            elif ttype == "area":
                if "name" not in target:
                    errors.append("area target requires name")

    return errors


def fallback_decision(packet: Dict[str, Any], reason: str) -> Dict[str, Any]:
    own_state = packet.get("own_state", {})
    pos = own_state.get("position", {})

    lat = pos.get("lat")
    lon = pos.get("lon")

    target = None
    if lat is not None and lon is not None:
        target = {"type": "point", "lat": lat, "lon": lon}

    return {
        "intent": "maintain_current_posture",
        "action": "hold",
        "target": target,
        "formation": "defensive",
        "tempo": "static",
        "engagement": "return_fire_only",
        "report_up": f"Fallback decision applied: {reason}",
        "order_text": "",
        "planning": {
            "needs_planning": False,
            "planning_time_s": 0,
            "reason": "fallback_decision",
        },
        "confidence": 0.2,
    }


def parse_and_validate(raw_text: str, packet: Dict[str, Any]) -> DecisionResult:
    try:
        d = parse_llm_json(raw_text)
    except Exception as e:
        fb = fallback_decision(packet, f"json_parse_error: {e}")
        return DecisionResult(
            ok=False,
            decision=fb,
            errors=[str(e)],
            raw_text=raw_text,
        )

    errors = validate_decision(d)

    if errors:
        fb = fallback_decision(packet, "validation_failed")
        return DecisionResult(
            ok=False,
            decision=fb,
            errors=errors,
            raw_text=raw_text,
        )

    return DecisionResult(
        ok=True,
        decision=d,
        errors=[],
        raw_text=raw_text,
    )
