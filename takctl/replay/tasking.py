from __future__ import annotations

from copy import deepcopy
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


def default_title_for_runtime_action(action: str, params: Dict[str, Any]) -> str:
    if action == "llm_replan_from_inbox":
        return "Läsa igenom meddelande"
    if action == "llm_replan_from_deadline":
        return "Ta nytt beslut efter avslutat arbete"
    if action == "llm_replan_from_world_change":
        return "Ta nytt beslut efter förändrad omvärldsbild"
    if action == "send_message":
        return f"Skicka meddelande till {params.get('recipient') or 'mottagare'}"
    if action == "move_unit":
        return "Förflytta enhet"
    if action == "change_posture":
        return f"Ändra hållning till {params.get('posture') or 'ny hållning'}"
    if action == "observe_area":
        return f"Observera {params.get('area') or 'område'}"
    if action == "hold_position":
        return "Hålla position"
    if action == "report_status":
        return f"Rapportera till {params.get('recipient') or 'överordnad'}"
    return action


def default_description_for_runtime_action(action: str, params: Dict[str, Any]) -> str:
    if action == "llm_replan_from_inbox":
        return "Enheten läser inkommet meddelande och tar fram ny arbetsbild."
    if action == "llm_replan_from_deadline":
        return "Enheten tar nytt beslut eftersom ett arbete har blivit klart eller nått sin beslutspunkt."
    if action == "llm_replan_from_world_change":
        return "Enheten tar nytt beslut eftersom omvärldsbilden har förändrats."
    if action == "send_message":
        return f"Meddelande ska skickas till {params.get('recipient') or 'mottagare'}."
    if action == "move_unit":
        return "Enheten ska förflytta sig enligt angivna parametrar."
    if action == "change_posture":
        return f"Enheten ska ändra hållning till {params.get('posture') or 'ny hållning'}."
    if action == "observe_area":
        return f"Enheten ska observera {params.get('area') or 'område'}."
    if action == "hold_position":
        return "Enheten ska hålla nuvarande eller angiven position."
    if action == "report_status":
        return f"Enheten ska rapportera status till {params.get('recipient') or 'överordnad'}."
    return action


def normalize_runtime_work_item(item: Dict[str, Any], sim_time_s: int) -> Dict[str, Any]:
    out = deepcopy(item)

    action = str(out.get("action") or "").strip()
    if action not in RUNTIME_ACTIONS:
        raise ValueError(f"invalid runtime action: {action}")
    out["action"] = action

    params = out.get("params")
    if not isinstance(params, dict):
        params = {}
    out["params"] = params

    status = str(out.get("status") or "pending").strip() or "pending"
    out["status"] = status

    title = str(out.get("title") or "").strip()
    if not title:
        title = default_title_for_runtime_action(action, params)
    out["title"] = title

    description = str(out.get("description") or "").strip()
    if not description:
        description = default_description_for_runtime_action(action, params)
    out["description"] = description

    duration_s = int(out.get("duration_s") or 0)
    out["duration_s"] = max(0, duration_s)

    out["created_sim_time_s"] = int(out.get("created_sim_time_s") or sim_time_s)

    started = out.get("started_sim_time_s")
    if status == "active":
        out["started_sim_time_s"] = int(started if started is not None else sim_time_s)
    else:
        out["started_sim_time_s"] = int(started) if started is not None else None

    deadline = out.get("deadline_sim_time_s")
    if deadline is None:
        base = out["started_sim_time_s"] if out["started_sim_time_s"] is not None else sim_time_s
        deadline = int(base) + int(out["duration_s"])
    out["deadline_sim_time_s"] = int(deadline)

    return out


def normalize_runtime_work(work: Any, sim_time_s: int) -> List[List[Dict[str, Any]]]:
    if not isinstance(work, list):
        raise ValueError("work must be list")
    out: List[List[Dict[str, Any]]] = []
    for chain in work:
        if not isinstance(chain, list) or not chain:
            continue
        norm_chain: List[Dict[str, Any]] = []
        for item in chain:
            if not isinstance(item, dict):
                raise ValueError("work item must be object")
            norm_chain.append(normalize_runtime_work_item(item, sim_time_s))
        if norm_chain:
            out.append(norm_chain)
    return out


def decision_to_work(decision: Dict[str, Any], sim_time_s: int) -> List[List[Dict[str, Any]]]:
    work = decision.get("work")
    return normalize_runtime_work(work, sim_time_s)
