"""Pure simulation state and validation; geographic coordinates are authoritative."""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import uuid
import xml.etree.ElementTree as ET

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


def relative_offset(anchor, p):
    return (math.radians(p["lat"]-anchor["lat"])*EARTH,
            math.radians(p["lon"]-anchor["lon"])*EARTH*math.cos(math.radians(anchor["lat"])))


def make_path(start, args):
    path = args.get("path")
    if not isinstance(path, list) or not 1 <= len(path) <= 100:
        raise ValueError("path requires 1..100 destination points")
    path = [dict(start)] + [point(p) for p in path]
    length = sum(distance(a,b) for a,b in zip(path,path[1:]))
    duration = number(args.get("duration_s"), "duration_s", 10, 86400)
    if not .1 <= length <= 100000 or length/duration > 60:
        raise ValueError("Path must be 0.1m..100km and speed <=60m/s")
    return {"id":str(uuid.uuid4()), "path":path, "distance_m":length, "duration_s":duration, "elapsed_s":0}


def advance_path(move, seconds):
    move["elapsed_s"] = min(move["duration_s"], move["elapsed_s"] + max(0,seconds))
    remaining = move["distance_m"]*move["elapsed_s"]/move["duration_s"]
    target = move["path"][-1]
    for a,b in zip(move["path"],move["path"][1:]):
        length=distance(a,b)
        if remaining <= length and length > 0:
            target=interpolate(a,b,remaining/length);break
        remaining -= length
    return dict(target), move["elapsed_s"] >= move["duration_s"]


def cot_type(value):
    if not isinstance(value,str) or not re.fullmatch(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+){1,20}",value):
        raise ValueError("Invalid CoT type")
    return value


def validate_cot(value, unit_id):
    if not isinstance(value,str) or len(value.encode())>16384 or "<!DOCTYPE" in value.upper() or "<!ENTITY" in value.upper():
        raise ValueError("Custom CoT must be <=16KiB without DTD/entities")
    try: root=ET.fromstring(value)
    except ET.ParseError as exc: raise ValueError("Invalid CoT XML") from exc
    if root.tag!="event" or not root.get("uid","").startswith("taks-custom:"+unit_id+":"):
        raise ValueError("Custom event UID must use taks-custom:UNIT_ID: namespace")
    if len(root.get("uid"))>160: raise ValueError("CoT UID too long")
    cot_type(root.get("type"))
    if len(list(root.iter("event"))) != 1: raise ValueError("Nested CoT events are not allowed")
    if len(root.findall("point")) != 1: raise ValueError("Exactly one point required")
    p=root.find("point")
    try: point({"lat":float(p.get("lat","")),"lon":float(p.get("lon",""))})
    except (TypeError,ValueError) as exc: raise ValueError("Valid CoT coordinates required") from exc
    for key, default, low, high in (("hae","0",-100000,100000),("ce","999999",0,1e9),("le","999999",0,1e9)):
        try: number(float(p.get(key,default)),key,low,high)
        except (TypeError,ValueError) as exc: raise ValueError("Invalid CoT point uncertainty/altitude") from exc
        p.set(key,p.get(key,default))
    if len(root.findall("detail"))>1: raise ValueError("At most one detail element allowed")
    detail=root.find("detail")
    if detail is None: detail=ET.SubElement(root,"detail")
    contact=detail.find("contact")
    if contact is not None and not contact.get("callsign","").startswith("SIM-"):
        raise ValueError("Custom callsign must be SIM-prefixed")
    remarks=detail.find("remarks")
    if remarks is None: remarks=ET.SubElement(detail,"remarks")
    remarks.text="SIMULATION ONLY | "+(remarks.text or "")
    root.set("version","2.0")
    root.set("how",root.get("how","m-g"))
    result=ET.tostring(root,encoding="unicode")
    if len(result.encode())>16384: raise ValueError("Normalized CoT exceeds 16KiB")
    return result


class World:
    def __init__(self, state=None, capacity=8):
        self.capacity = capacity
        self.state = copy.deepcopy(state) if state else {
            "schema": 1, "revision": 0, "units": {}, "requests": {}, "events": []}
        if self.state.get("schema") != 1:
            raise ValueError("Unsupported simulation state schema")
        self.state.setdefault("markers", {})
        self.state.setdefault("cot_templates", {})

    def event(self, kind, **fields):
        self.state["revision"] += 1
        row = {"revision": self.state["revision"], "kind": kind, **fields}
        self.state["events"] = (self.state["events"] + [row])[-200:]

    def entities(self):
        return [e for u in self.state["units"].values() if u["active"] for e in u["entities"]]

    def advance(self, seconds):
        changed = False
        for u in self.state["units"].values():
            if not u["active"]:
                continue
            individual = False
            for e in u["entities"]:
                move = e.get("move")
                if move:
                    e["position"], finished = advance_path(move, seconds)
                    individual = changed = True
                    if finished:
                        e["move"] = None
                        self.event("entity_move_completed", unit_id=u["id"], entity_id=e["id"], action_id=move["id"])
            if individual and not u.get("move"):
                u["position"] = dict(u["entities"][0]["position"])
                for e in u["entities"]:
                    e["north_m"], e["east_m"] = relative_offset(u["position"], e["position"])
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
                if e.get("health_state", "fit") == "fit":
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
        if op == "batch":
            if set(a) - {"request_id", "expected_revision", "commands"}:
                raise ValueError("Unknown batch arguments")
            commands = a.get("commands")
            if not isinstance(commands, list) or not 1 <= len(commands) <= 32:
                raise ValueError("Batch requires 1..32 commands")
            results = []
            for command in commands:
                if not isinstance(command, dict) or set(command) != {"operation", "arguments"}:
                    raise ValueError("Invalid batch command")
                if command["operation"] in ("batch", "chat", "cot_send"):
                    raise ValueError("Network sends and nested batches are not allowed inside a state batch")
                if not isinstance(command["arguments"], dict) or {"request_id", "expected_revision"} & set(command["arguments"]):
                    raise ValueError("Batch children must not have request/revision fields")
                results.append(self._apply(command["operation"], command["arguments"]))
            return {"results": results}
        common = {"request_id", "expected_revision", "unit_id"}
        allowed = {"create": {"count", "position", "callsign", "tak_unit_ref"},
                   "move": {"path", "duration_s"}, "stop": set(), "deactivate": set(),
                   "chat": {"message", "entity_id", "target_uid", "target_callsign"},
                   "entity_move": {"entity_id", "path", "duration_s"},
                   "entity_stop": {"entity_id"},
                   "entity_patch": {"entity_id", "health_state", "remarks", "cot_type"},
                   "marker_put": {"marker_id", "position", "callsign", "cot_type", "remarks"},
                   "marker_remove": {"marker_id"},
                   "cot_send": {"entity_id", "xml", "persist"}}
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
        if op in ("marker_put", "marker_remove"):
            mid = a.get("marker_id", "")
            if not isinstance(mid, str) or not ID.fullmatch(mid):
                raise ValueError("Invalid marker_id")
            key = uid + ":" + mid
            if op == "marker_remove":
                if key not in self.state["markers"]:
                    raise ValueError("Marker not found")
                self.state["markers"][key]["active"] = False
            else:
                if key not in self.state["markers"] and len(self.state["markers"]) >= 64:
                    raise ValueError("Marker capacity exceeded")
                label, remarks = a.get("callsign", ""), a.get("remarks", "")
                if not isinstance(label, str) or not re.fullmatch(r"SIM-[A-Z0-9-]{1,40}", label):
                    raise ValueError("Marker callsign must be SIM-prefixed")
                if not isinstance(remarks, str) or len(remarks) > 1000:
                    raise ValueError("Invalid marker remarks")
                self.state["markers"][key] = {"id": mid, "uid": "taks-marker:" + key,
                    "unit_id": uid, "active": True, "callsign": label, "position": point(a.get("position")),
                    "cot_type": cot_type(a.get("cot_type", "a-u-G")), "remarks": remarks,
                    "role": "exercise marker", "readiness": "simulated", "sender_entity_id": unit["entities"][0]["id"]}
            self.event("marker_updated", unit_id=uid, marker_id=mid)
            return {"marker_id": mid, "uid": "taks-marker:" + key}
        if op in ("entity_move", "entity_stop", "entity_patch", "cot_send"):
            entity = next((e for e in unit["entities"] if e["id"] == a.get("entity_id")), None)
            if entity is None:
                raise ValueError("Entity not found")
            if op == "entity_move":
                if unit.get("move"):
                    raise ValueError("Stop the unit move before individual movement")
                if entity.get("health_state", "fit") != "fit":
                    raise ValueError("A wounded/KIA entity cannot start an unassisted move")
                entity["move"] = make_path(entity["position"], a)
                self.event("entity_move_started", unit_id=uid, entity_id=entity["id"], action_id=entity["move"]["id"])
                return {"entity_id": entity["id"], "action_id": entity["move"]["id"], "duration_s": entity["move"]["duration_s"]}
            if op == "entity_stop":
                if unit.get("move"):
                    raise ValueError("Stop unit movement before stopping an individual")
                entity["move"] = None
            elif op == "entity_patch":
                if "health_state" in a:
                    if a["health_state"] not in ("fit", "wounded", "kia"):
                        raise ValueError("Invalid health_state")
                    entity["health_state"] = a["health_state"]
                    entity["readiness"] = "ready" if a["health_state"] == "fit" else a["health_state"]
                    if a["health_state"] != "fit": entity["move"] = None
                if "cot_type" in a: entity["cot_type"] = cot_type(a["cot_type"])
                if "remarks" in a:
                    if not isinstance(a["remarks"], str) or len(a["remarks"]) > 1000:
                        raise ValueError("Invalid entity remarks")
                    entity["remarks"] = a["remarks"]
            else:
                xml = validate_cot(a.get("xml"), uid)
                persist = a.get("persist", False)
                if type(persist) is not bool: raise ValueError("persist must be boolean")
                root = ET.fromstring(xml)
                if persist:
                    if root.get("type") == "b-t-f": raise ValueError("GeoChat must not be repeatedly published")
                    key = root.get("uid")
                    if key not in self.state["cot_templates"] and len(self.state["cot_templates"]) >= 16:
                        raise ValueError("Persistent CoT capacity exceeded")
                    self.state["cot_templates"][key] = {"xml": xml, "unit_id": uid, "sender_entity_id": entity["id"]}
                self.event("cot_requested", unit_id=uid, entity_id=entity["id"], cot_uid=root.get("uid"))
                return {"entity_id": entity["id"], "cot_xml": xml, "persist": persist, "delivery": "pending"}
            self.event("entity_updated", unit_id=uid, entity_id=entity["id"])
            return {"entity_id": entity["id"]}
        if op == "move":
            if any(e.get("move") for e in unit["entities"]):
                raise ValueError("Stop individual movement before a unit move")
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
            for e in unit["entities"]: e["move"] = None
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
