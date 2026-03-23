from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List


def _ensure_list(d: Dict[str, Any], key: str) -> List[Any]:
    v = d.get(key)
    if isinstance(v, list):
        return v
    d[key] = []
    return d[key]


def validate_referee_outcome(data: Dict[str, Any]) -> None:
    required = [
        "summary",
        "activity_result",
        "position_update",
        "time_effects",
        "friction",
        "observations",
        "contact",
        "casualties",
        "state_patch",
        "confidence",
    ]
    for key in required:
        if key not in data:
            raise ValueError(f"missing referee field: {key}")


def apply_referee_outcome(state: Dict[str, Any], outcome: Dict[str, Any], sim_time_s: int) -> Dict[str, Any]:
    validate_referee_outcome(outcome)

    s = deepcopy(state)

    patch = outcome.get("state_patch") or {}
    own_patch = patch.get("own_state") or {}

    own_state = s.setdefault("own_state", {})
    own_state.update(own_patch)

    constraints_add = patch.get("constraints_add") or []
    observations_add = patch.get("observations_add") or []
    private_referee_add = patch.get("private_referee_add") or []
    pending_report_items_add = patch.get("pending_report_items_add") or []

    _ensure_list(s, "constraints").extend(constraints_add)
    _ensure_list(s, "observations").extend(observations_add)
    _ensure_list(s, "private_referee").extend(private_referee_add)

    pri = _ensure_list(s, "pending_report_items")
    for item in pending_report_items_add:
        pri.append({
            "sim_time_s": sim_time_s,
            "severity": "info",
            "text": str(item),
        })

    current_activity = s.setdefault("current_activity", {})
    if outcome.get("activity_result") in {"completed", "aborted", "blocked"}:
        current_activity["status"] = "inactive"
    else:
        current_activity["status"] = "active"

    pos_update = outcome.get("position_update") or {}
    if "to" in pos_update:
        current_activity["last_progress_sim_time_s"] = sim_time_s

    s["last_referee_outcome"] = {
        "sim_time_s": sim_time_s,
        "summary": outcome.get("summary", ""),
        "activity_result": outcome.get("activity_result", "no_change"),
    }

    return s
