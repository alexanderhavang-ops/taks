from __future__ import annotations

from typing import Any, Dict, List

from .referee_guardrails import build_constraints


def _copy_position(v: Any) -> Dict[str, float]:
    if not isinstance(v, dict):
        return {"lat": 0.0, "lon": 0.0}
    return {
        "lat": float(v.get("lat", 0.0)),
        "lon": float(v.get("lon", 0.0)),
    }


def build_referee_packet(
    state: Dict[str, Any],
    sim_time_s: int,
    tick_length_s: int,
    weather: Dict[str, Any] | None = None,
    terrain: Dict[str, Any] | None = None,
    known_threats: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    weather = weather or {}
    terrain = terrain or {}
    known_threats = known_threats or []

    agent = state.get("agent") or {}
    own_state = state.get("own_state") or {}
    current_activity = state.get("current_activity") or {}
    private_referee = state.get("private_referee") or []

    packet = {
        "sim_time_s": sim_time_s,
        "tick_length_s": tick_length_s,
        "unit": {
            "callsign": agent.get("callsign", ""),
            "side": agent.get("side", "blue"),
            "role": agent.get("role", ""),
            "echelon": agent.get("echelon", ""),
            "control_mode": agent.get("control_mode", "ai"),
            "position": _copy_position(own_state.get("position")),
            "readiness": own_state.get("readiness", ""),
            "posture": own_state.get("posture", ""),
            "combat_value": own_state.get("combat_value", 1.0),
            "strength": own_state.get("strength", 0),
            "fatigue": own_state.get("fatigue", 0.0),
            "mobility": own_state.get("mobility", {}),
        },
        "activity": {
            "type": current_activity.get("type", "idle"),
            "status": current_activity.get("status", "idle"),
            "intent": current_activity.get("intent", ""),
            "from": _copy_position(current_activity.get("from") or own_state.get("position")),
            "to": _copy_position(current_activity.get("to") or own_state.get("position")),
            "route_hint": current_activity.get("route_hint", ""),
            "tempo": current_activity.get("tempo", ""),
            "formation": current_activity.get("formation", ""),
            "started_sim_time_s": current_activity.get("started_sim_time_s", sim_time_s),
            "last_progress_sim_time_s": current_activity.get("last_progress_sim_time_s", sim_time_s),
        },
        "context": {
            "weather": weather,
            "time_of_day": "day",
            "terrain": terrain,
            "known_threats": known_threats,
            "friendly_nearby": [],
            "recent_referee_effects": private_referee[-5:],
        },
        "constraints": build_constraints(state, tick_length_s),
    }
    return packet
