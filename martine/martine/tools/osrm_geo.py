from __future__ import annotations

import os
from typing import Any, Dict, List, Tuple

import requests


def _osrm_base_url() -> str:
    return os.environ.get("MARTINE_OSRM_URL", "http://127.0.0.1:8080/api/geo/osrm").rstrip("/")


def _validate_profile(profile: str) -> str:
    p = (profile or "foot").strip().lower()
    if p not in {"foot", "car", "bike"}:
        raise ValueError(f"unsupported profile: {profile}")
    return p


def _validate_point(name: str, lat: float, lon: float) -> Tuple[float, float]:
    la = float(lat)
    lo = float(lon)
    if not (-90.0 <= la <= 90.0):
        raise ValueError(f"{name}.lat out of range")
    if not (-180.0 <= lo <= 180.0):
        raise ValueError(f"{name}.lon out of range")
    return la, lo


def _coords(lon: float, lat: float) -> str:
    return f"{lon:.6f},{lat:.6f}"


def _simplify_route(route: Dict[str, Any], idx: int) -> Dict[str, Any]:
    legs = route.get("legs") or []
    steps: List[Dict[str, Any]] = []
    for leg in legs:
        for st in leg.get("steps") or []:
            maneuver = st.get("maneuver") or {}
            steps.append(
                {
                    "distance_m": round(float(st.get("distance") or 0.0), 1),
                    "duration_s": round(float(st.get("duration") or 0.0), 1),
                    "name": st.get("name") or "",
                    "mode": st.get("mode") or "",
                    "maneuver_type": maneuver.get("type") or "",
                    "maneuver_modifier": maneuver.get("modifier") or "",
                    "location": maneuver.get("location") or [],
                }
            )

    return {
        "route_id": f"route_{idx + 1}",
        "distance_m": round(float(route.get("distance") or 0.0), 1),
        "duration_s": round(float(route.get("duration") or 0.0), 1),
        "geometry": route.get("geometry") or "",
        "legs": len(legs),
        "steps": steps,
    }


def route_between_points(
    from_lat: float,
    from_lon: float,
    to_lat: float,
    to_lon: float,
    profile: str = "foot",
) -> Dict[str, Any]:
    p = _validate_profile(profile)
    fla, flo = _validate_point("from", from_lat, from_lon)
    tla, tlo = _validate_point("to", to_lat, to_lon)

    url = (
        f"{_osrm_base_url()}/route/v1/{p}/"
        f"{_coords(flo, fla)};{_coords(tlo, tla)}"
    )
    params = {
        "overview": "full",
        "geometries": "geojson",
        "steps": "true",
        "alternatives": "false",
    }

    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    body = r.json()

    routes = body.get("routes") or []
    if not routes:
        return {
            "ok": False,
            "tool": "route_between_points",
            "error": "no route returned",
            "profile": p,
            "from": {"lat": fla, "lon": flo},
            "to": {"lat": tla, "lon": tlo},
            "osrm_url": url,
        }

    return {
        "ok": True,
        "tool": "route_between_points",
        "profile": p,
        "from": {"lat": fla, "lon": flo},
        "to": {"lat": tla, "lon": tlo},
        "route": _simplify_route(routes[0], 0),
        "waypoints": body.get("waypoints") or [],
        "code": body.get("code") or "",
    }


def route_alternatives_between_points(
    from_lat: float,
    from_lon: float,
    to_lat: float,
    to_lon: float,
    profile: str = "foot",
    max_alternatives: int = 3,
) -> Dict[str, Any]:
    p = _validate_profile(profile)
    fla, flo = _validate_point("from", from_lat, from_lon)
    tla, tlo = _validate_point("to", to_lat, to_lon)
    limit = max(1, min(int(max_alternatives), 5))

    url = (
        f"{_osrm_base_url()}/route/v1/{p}/"
        f"{_coords(flo, fla)};{_coords(tlo, tla)}"
    )
    params = {
        "overview": "full",
        "geometries": "geojson",
        "steps": "true",
        "alternatives": "true",
    }

    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    body = r.json()

    routes = body.get("routes") or []
    out = [_simplify_route(rt, i) for i, rt in enumerate(routes[:limit])]

    return {
        "ok": bool(out),
        "tool": "route_alternatives_between_points",
        "profile": p,
        "from": {"lat": fla, "lon": flo},
        "to": {"lat": tla, "lon": tlo},
        "routes": out,
        "waypoints": body.get("waypoints") or [],
        "code": body.get("code") or "",
    }


def snap_point_to_network(
    lat: float,
    lon: float,
    profile: str = "foot",
    number: int = 1,
) -> Dict[str, Any]:
    p = _validate_profile(profile)
    la, lo = _validate_point("point", lat, lon)
    n = max(1, min(int(number), 5))

    url = f"{_osrm_base_url()}/nearest/v1/{p}/{_coords(lo, la)}"
    params = {
        "number": str(n),
    }

    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    body = r.json()

    return {
        "ok": True,
        "tool": "snap_point_to_network",
        "profile": p,
        "point": {"lat": la, "lon": lo},
        "waypoints": body.get("waypoints") or [],
        "code": body.get("code") or "",
    }
