from __future__ import annotations

from math import atan2, cos, radians, sin, sqrt
from typing import Any, Dict


EARTH_RADIUS_KM = 6371.0


def _f(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def haversine_km(a: Dict[str, Any], b: Dict[str, Any]) -> float:
    lat1 = radians(_f(a.get("lat")))
    lon1 = radians(_f(a.get("lon")))
    lat2 = radians(_f(b.get("lat")))
    lon2 = radians(_f(b.get("lon")))

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    x = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(x), sqrt(1 - x))
    return EARTH_RADIUS_KM * c


def compute_max_distance_km(state: Dict[str, Any], tick_length_s: int) -> float:
    own_state = state.get("own_state") or {}
    mobility = own_state.get("mobility") or {}
    max_speed_kph = _f(mobility.get("max_speed_kph"), 0.0)

    readiness = str(own_state.get("readiness") or "").strip().lower()
    posture = str(own_state.get("posture") or "").strip().lower()
    fatigue = _f(own_state.get("fatigue"), 0.0)

    speed_factor = 1.0

    if readiness in {"stridsberedskap", "combat"}:
        speed_factor *= 0.7

    if posture in {"line", "deployed"}:
        speed_factor *= 0.8

    if fatigue > 0.7:
        speed_factor *= 0.7
    elif fatigue > 0.4:
        speed_factor *= 0.85

    hours = float(tick_length_s) / 3600.0
    raw = max_speed_kph * speed_factor * hours

    # Liten säkerhetsmarginal så referee inte trycker till max jämt.
    return round(raw * 0.85, 3)


def build_constraints(state: Dict[str, Any], tick_length_s: int) -> Dict[str, Any]:
    return {
        "must_not_exceed_max_distance_km": compute_max_distance_km(state, tick_length_s),
        "must_remain_plausible": True,
        "no_teleportation": True,
        "no_unjustified_casualties": True,
        "allowed_observation_types": ["air", "ground", "signal", "none"],
    }
