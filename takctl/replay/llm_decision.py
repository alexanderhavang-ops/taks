from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List


RUNTIME_ACTIONS = {
    "llm_replan_from_inbox",
    "llm_replan_from_deadline",
    "llm_replan_from_world_change",
    "send_message",
    "move_unit",
    "change_posture",
    "observe_area",
    "hold_position",
    "report_status",
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
    constraints: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "sim_time_s": int(sim_time_s),
        "agent": agent,
        "own_state": own_state,
        "subordinates": subordinates,
        "observations": observations,
        "constraints": constraints,
    }


def parse_llm_json(raw_text: str) -> Dict[str, Any]:
    s = raw_text.strip()
    if s.startswith("```"):
        lines = s.splitlines()
        if len(lines) >= 3:
            s = "\n".join(lines[1:-1]).strip()
    return json.loads(s)


def validate_runtime_work_item(item: Dict[str, Any]) -> List[str]:
    errors: List[str] = []

    action = str(item.get("action") or "")
    if action not in RUNTIME_ACTIONS:
        errors.append(f"invalid runtime work action: {action}")

    params = item.get("params")
    if not isinstance(params, dict):
        errors.append("work item params must be object")

    title = item.get("title")
    if title is not None and not isinstance(title, str):
        errors.append("work item title must be string")

    description = item.get("description")
    if description is not None and not isinstance(description, str):
        errors.append("work item description must be string")

    status = item.get("status")
    if status is not None and not isinstance(status, str):
        errors.append("work item status must be string")

    duration_s = item.get("duration_s")
    if duration_s is not None and (not isinstance(duration_s, int) or duration_s < 0):
        errors.append("work item duration_s must be int >= 0")

    return errors


def validate_decision(d: Dict[str, Any]) -> List[str]:
    errors: List[str] = []

    work = d.get("work")
    if not isinstance(work, list):
        return ["work must be list"]

    for i, chain in enumerate(work):
        if not isinstance(chain, list):
            errors.append(f"work[{i}] must be list")
            continue
        if not chain:
            continue
        for j, item in enumerate(chain):
            if not isinstance(item, dict):
                errors.append(f"work[{i}][{j}] must be object")
                continue
            for e in validate_runtime_work_item(item):
                errors.append(f"work[{i}][{j}]: {e}")

    return errors


def fallback_decision(packet: Dict[str, Any], reason: str) -> Dict[str, Any]:
    own_state = packet.get("own_state", {})
    pos = own_state.get("position", {})

    work: List[List[Dict[str, Any]]] = [
        [
            {
                "title": "Ta nytt beslut efter fel",
                "description": f"Fallback efter fel i LLM-svar: {reason}",
                "action": "llm_replan_from_deadline",
                "params": {},
                "status": "active",
                "duration_s": 60,
            }
        ]
    ]

    if isinstance(pos, dict) and pos.get("lat") is not None and pos.get("lon") is not None:
        work.append([
            {
                "title": "Hålla nuvarande position",
                "description": "Enheten håller nuvarande position tills nytt beslut finns.",
                "action": "hold_position",
                "params": {
                    "lat": pos.get("lat"),
                    "lon": pos.get("lon"),
                },
                "status": "pending",
                "duration_s": 300,
            }
        ])

    return {"work": work}


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
