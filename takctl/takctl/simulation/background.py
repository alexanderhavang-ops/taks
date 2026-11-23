"""Deterministic, persisted routes. Movement follows only supplied waypoints."""
from bisect import bisect_right
from operator import itemgetter

from .model import distance, interpolate, make_path, number

MAX_WAYPOINTS = 512


def policy(start, args):
    rows = args.get("waypoints")
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_WAYPOINTS:
        raise ValueError(f"waypoints requires 1..{MAX_WAYPOINTS} position/travel_s/wait_s entries")
    repeat = args.get("repeat", False)
    if type(repeat) is not bool:
        raise ValueError("repeat must be boolean")

    route, cursor, duration = [], dict(start), 0
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"position", "travel_s", "wait_s"}:
            raise ValueError("Each waypoint needs position, travel_s and wait_s")
        move = make_path(cursor, {"path": [row["position"]], "duration_s": row["travel_s"]})
        duration += move["duration_s"] + number(row["wait_s"], "wait_s", 0, 86400)
        cursor = move["path"][-1]
        route.append((duration, move["duration_s"], cursor["lat"], cursor["lon"]))
    if repeat and distance(start, cursor) > .1:
        raise ValueError("Repeating routes must return to their starting position")
    return {"enabled": True, "repeat": repeat, "delay_s": number(args.get("delay_s", 0), "delay_s", 0, 86400),
            "elapsed_s": 0, "cycle_s": duration, "origin": dict(start), "route": route,
            "phase": "waiting", "cycles": 0}


def waypoints(policy):
    return ({"lat": lat, "lon": lon} for _, _, lat, lon in policy["route"])


def summary(policy):
    if policy is None:
        return None
    return {**{k: v for k, v in policy.items() if k not in ("legs", "route", "origin")},
            "waypoint_count": len(policy.get("route", policy.get("legs", ())))}


def suspend(owner):
    if owner.get("background"):
        owner["background"]["enabled"] = False


def route_position(policy, elapsed):
    if "route" not in policy:
        # Upgrade routes saved by earlier SimKeeper versions without resetting progress.
        legs = policy.pop("legs")
        policy["origin"] = legs[0]["move"]["path"][0]
        duration = 0
        policy["route"] = []
        for leg in legs:
            move = leg["move"]
            duration += move["duration_s"] + leg["wait_s"]
            end = move["path"][-1]
            policy["route"].append((duration, move["duration_s"], end["lat"], end["lon"]))

    if elapsed < 0:
        return dict(policy["origin"]), None, "waiting"
    route = policy["route"]
    index = bisect_right(route, elapsed, key=itemgetter(0))
    if index == len(route):
        _, _, lat, lon = route[-1]
        return {"lat": lat, "lon": lon}, index - 1, "completed"
    _, travel, lat, lon = route[index]
    destination = {"lat": lat, "lon": lon}
    if index:
        prior_end, _, start_lat, start_lon = route[index - 1]
        start = {"lat": start_lat, "lon": start_lon}
    else:
        prior_end, start = 0, policy["origin"]
    leg_elapsed = elapsed - prior_end
    if leg_elapsed >= travel:
        return destination, index, "waiting"
    return interpolate(start, destination, leg_elapsed / travel), index, "moving"


def progress(policy):
    elapsed = policy["elapsed_s"] - policy["delay_s"]
    if policy["repeat"] and elapsed >= 0:
        cycles, elapsed = divmod(elapsed, policy["cycle_s"])
        policy["cycles"] = int(cycles)
    return route_position(policy, elapsed)


def advance(owner, seconds):
    policy = owner.get("background")
    if not policy or not policy["enabled"] or owner.get("move") or owner.get("health_state", "fit") != "fit":
        return False
    policy["elapsed_s"] += seconds
    position, index, phase = progress(policy)
    owner["position"] = position
    policy.update(phase=phase, waypoint_index=index)
    if phase == "completed":
        policy.update(enabled=False, elapsed_s=policy["delay_s"] + policy["cycle_s"])
    return True
