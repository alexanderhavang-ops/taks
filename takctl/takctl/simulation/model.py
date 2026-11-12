"""Pure simulation state and validation; geographic coordinates are authoritative."""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import uuid

ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,31}\Z")
EARTH = 6371008.8


def number(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise ValueError(f"{name} must be a number")
    value = float(value)
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{name} must be {low}..{high}")
    return value


def point(value):
    if not isinstance(value, dict) or set(value) != {"lat", "lon"}:
        raise ValueError("point requires exactly lat and lon")
    return {"lat": number(value["lat"], "lat", -85, 85),
            "lon": number(value["lon"], "lon", -180, 180)}


def distance(a, b):
    p, q = math.radians(a["lat"]), math.radians(b["lat"])
    dp, dq = q - p, math.radians(b["lon"] - a["lon"])
    h = math.sin(dp / 2)**2 + math.cos(p)*math.cos(q)*math.sin(dq / 2)**2
    return 2 * EARTH * math.asin(min(1, math.sqrt(h)))


def offset(p, north, east):
    return point({"lat": p["lat"] + math.degrees(north / EARTH),
                  "lon": p["lon"] + math.degrees(east / (EARTH * math.cos(math.radians(p["lat"])) ))})


def interpolate(a, b, f):
    # Spherical interpolation keeps longitudes correct at the date line.
    def xyz(p):
        la, lo = math.radians(p["lat"]), math.radians(p["lon"])
        return (math.cos(la)*math.cos(lo), math.cos(la)*math.sin(lo), math.sin(la))
    u, v = xyz(a), xyz(b)
    angle = distance(a, b) / EARTH
    if angle < 1e-12:
        return dict(b)
    x = math.sin((1-f)*angle) / math.sin(angle)
    y = math.sin(f*angle) / math.sin(angle)
    w = [x*u[i] + y*v[i] for i in range(3)]
    return {"lat": math.degrees(math.atan2(w[2], math.hypot(w[0], w[1]))),
            "lon": math.degrees(math.atan2(w[1], w[0]))}


class World:
    def __init__(self, state=None, capacity=8):
        self.capacity = capacity
        self.state = copy.deepcopy(state) if state else {
            "schema": 1, "revision": 0, "units": {}, "requests": {}, "events": []}
        if self.state.get("schema") != 1:
            raise ValueError("Unsupported simulation state schema")

    def event(self, kind, **fields):
        self.state["revision"] += 1
        row = {"revision": self.state["revision"], "kind": kind, **fields}
        self.state["events"] = (self.state["events"] + [row])[-200:]

    def entities(self):
        return [e for u in self.state["units"].values() if u["active"] for e in u["entities"]]

    def advance(self, seconds):
        changed = False
        for u in self.state["units"].values():
            move = u.get("move")
            if not u["active"] or not move:
                continue
            move["elapsed_s"] = min(move["duration_s"], move["elapsed_s"] + max(0, seconds))
            walked = move["distance_m"] * move["elapsed_s"] / move["duration_s"]
            path = move["path"]
            target = path[-1]
            for a, b in zip(path, path[1:]):
                length = distance(a, b)
                if walked <= length and length > 0:
                    target = interpolate(a, b, walked / length)
                    break
                walked -= length
            u["position"] = dict(target)
            for e in u["entities"]:
                e["position"] = offset(target, e["north_m"], e["east_m"])
            changed = True
            if move["elapsed_s"] >= move["duration_s"]:
                u["move"] = None
                self.event("move_completed", unit_id=u["id"], action_id=move["id"])
        return changed

    def apply(self, operation, args):
        """Validate and commit all state changes together; retries do not repeat actions."""
        if not isinstance(args, dict):
            raise ValueError("arguments must be an object")
        key = args.get("request_id")
        if not isinstance(key, str) or not ID.fullmatch(key):
            raise ValueError("request_id is required (1..32 letters, digits, _ or -)")
        fingerprint = hashlib.sha256(json.dumps([operation, args], sort_keys=True, allow_nan=False).encode()).hexdigest()
        previous = self.state["requests"].get(key)
        if previous:
            if previous["fingerprint"] != fingerprint:
                raise ValueError("request_id already used for different arguments")
            return {**previous["result"], "duplicate": True}
        if type(args.get("expected_revision")) is not int or args["expected_revision"] != self.state["revision"]:
            raise ValueError(f"expected_revision must match {self.state['revision']}")
        trial = World(self.state, self.capacity)
        result = trial._apply(operation, args)
        result.update(ok=True, revision=trial.state["revision"])
        trial.state["requests"][key] = {"fingerprint": fingerprint, "result": result}
        # Bounded retry history; callers must use new IDs for new commands.
        while len(trial.state["requests"]) > 512:
            del trial.state["requests"][next(iter(trial.state["requests"]))]
        self.state = trial.state
        return result

    def _apply(self, op, a):
        common = {"request_id", "expected_revision", "unit_id"}
        allowed = {"create": {"count", "position", "callsign", "tak_unit_ref"},
                   "move": {"path", "duration_s"}, "stop": set(), "deactivate": set(),
                   "chat": {"message", "entity_id", "target_uid", "target_callsign"}}
        if op not in allowed or set(a) - common - allowed[op]:
            raise ValueError("Unknown operation or arguments")
        uid = a.get("unit_id")
        if not isinstance(uid, str) or not ID.fullmatch(uid):
            raise ValueError("Invalid unit_id")
        if op == "create":
            if uid in self.state["units"]:
                raise ValueError("unit_id already exists; use a new ID")
            count = a.get("count", 4)
            if type(count) is not int or not 1 <= count <= self.capacity:
                raise ValueError("count exceeds provisioned identity capacity")
            used_slots = {e["identity_slot"] for e in self.entities()}
            free_slots = sorted(set(range(self.capacity)) - used_slots)
            if len(free_slots) < count:
                raise ValueError("Identity pool exhausted; extend pool before adding units")
            if len(self.state["units"]) >= 128:
                raise ValueError("Exercise history full; archive before adding units")
            pos = point(a.get("position"))
            label = a.get("callsign", "SIM-DEMO")
            if not isinstance(label, str) or not re.fullmatch(r"SIM-[A-Z0-9-]{1,20}", label):
                raise ValueError("callsign must begin SIM- and use uppercase letters/digits/hyphens")
            ref = a.get("tak_unit_ref", "")
            if not isinstance(ref, str) or len(ref) > 128:
                raise ValueError("Invalid tak_unit_ref")
            entities = []
            for i in range(count):
                north, east = (0, 0) if i == 0 else (-10 * ((i+1)//2), 8 * (1 if i % 2 else -1))
                entities.append({"id": f"{uid}-{i+1:02d}", "uid": f"taks-sim:{uid}:{i+1:02d}",
                                 "callsign": f"{label}-{'HQ' if i == 0 else f'{i:02d}'}",
                                 "identity_slot": free_slots[i], "north_m": north, "east_m": east,
                                 "position": offset(pos, north, east), "role": "HQ" if i == 0 else "member",
                                 "readiness": "ready"})
            self.state["units"][uid] = {"id": uid, "callsign": label, "active": True,
                "tak_unit_ref": ref, "position": pos, "entities": entities, "move": None}
            self.event("unit_created", unit_id=uid, count=count)
            return {"unit_id": uid, "entities": [e["callsign"] for e in entities]}
        unit = self.state["units"].get(uid)
        if not unit or not unit["active"]:
            raise ValueError("Active unit not found")
        if op == "move":
            path = a.get("path")
            if not isinstance(path, list) or not 1 <= len(path) <= 100:
                raise ValueError("path must contain 1..100 destination waypoints")
            path = [dict(unit["position"])] + [point(p) for p in path]
            length = sum(distance(x, y) for x, y in zip(path, path[1:]))
            duration = number(a.get("duration_s"), "duration_s", 10, 86400)
            if not 0.1 <= length <= 100000 or length / duration > 60:
                raise ValueError("Path must be 0.1m..100km and speed <=60 m/s")
            # Validate member offsets at all endpoints before committing anything.
            for p in path:
                for e in unit["entities"]:
                    offset(p, e["north_m"], e["east_m"])
            action = str(uuid.uuid4())
            unit["move"] = {"id": action, "path": path, "distance_m": length,
                            "duration_s": duration, "elapsed_s": 0}
            self.event("move_started", unit_id=uid, action_id=action)
            return {"unit_id": uid, "action_id": action, "distance_m": round(length, 1), "duration_s": duration}
        if op in ("stop", "deactivate"):
            unit["move"] = None
            if op == "deactivate":
                unit["active"] = False
            self.event("movement_stopped" if op == "stop" else "unit_deactivated", unit_id=uid)
            return {"unit_id": uid, "active": unit["active"]}
        entity = next((e for e in unit["entities"] if e["id"] == a.get("entity_id", unit["entities"][0]["id"])), None)
        message = a.get("message")
        if entity is None or not isinstance(message, str) or not message.strip() or len(message) > 1000:
            raise ValueError("Valid entity and message of 1..1000 characters required")
        for field in ("target_uid", "target_callsign"):
            val = a.get(field, "All Chat Rooms")
            if not isinstance(val, str) or not 1 <= len(val) <= 128:
                raise ValueError(f"Invalid {field}")
        message_id = str(uuid.uuid4())
        self.event("chat_requested", unit_id=uid, message_id=message_id)
        return {"unit_id": uid, "message_id": message_id, "entity_id": entity["id"],
                "delivery": "pending", "message": message,
                "target_uid": a.get("target_uid", "All Chat Rooms"),
                "target_callsign": a.get("target_callsign", "All Chat Rooms")}
