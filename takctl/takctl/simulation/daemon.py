"""One asyncio process owns all TLS sessions and explicit exercise actions."""
from __future__ import annotations

import argparse
import asyncio
import copy
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import random
import resource
import signal
import shutil
import ssl
import time
import xml.etree.ElementTree as ET

from .model import World, advance_path
from .perception import PerceptionStore

SOCKET = "/opt/tak/simulation/control.sock"
MAX_REQUEST = 65536


class CotFrames:
    """Bounded CoT XML stream framing; TAK may repeat XML declarations.

    A TCP read is neither an event boundary nor necessarily a UTF-8 boundary.
    Ignore inter-event declarations and parse only complete event documents.
    """
    def __init__(self, accept=None):
        self.buffer = bytearray()
        self.accept = accept
        self.frames_seen = 0

    def feed(self, data):
        self.buffer.extend(data)
        frames = []
        while True:
            start = self.buffer.find(b"<event")
            if start < 0:
                if len(self.buffer) > 1048576:
                    raise ValueError("Inbound CoT framing exceeds memory bound")
                break
            if start:
                del self.buffer[:start]
            opening = self.buffer.find(b">")
            end = self.buffer.find(b"</event>")
            if opening >= 0 and self.buffer[opening-1:opening] == b"/":
                stop = opening + 1
            elif end >= 0:
                stop = end + len(b"</event>")
            else:
                if len(self.buffer) > 1048576:
                    raise ValueError("Inbound event exceeds memory bound")
                break
            if stop > 1048576:
                raise ValueError("Inbound event exceeds memory bound")
            frame = bytes(self.buffer[:stop])
            del self.buffer[:stop]
            self.frames_seen += 1
            if self.accept is None or self.accept(frame):
                frames.append(ET.fromstring(frame))
        return frames


def stamp(t):
    return t.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def course(entity):
    movement = entity.get("move")
    if not movement: return entity.get("course_deg", 0)
    start = entity["position"]; target, _ = advance_path(copy.deepcopy(movement), 1)
    a, b = math.radians(start["lat"]), math.radians(target["lat"])
    delta = math.radians(target["lon"] - start["lon"])
    return (math.degrees(math.atan2(math.sin(delta)*math.cos(b), math.cos(a)*math.sin(b)-math.sin(a)*math.cos(b)*math.cos(delta)))+360)%360


def event(entity, *, message=None, paused=False):
    now = datetime.now(timezone.utc)
    uid, callsign = entity["uid"], entity["callsign"]
    health = entity.get("health_state", "fit")
    display_callsign = callsign + (" [WIA]" if health == "wounded" else " [KIA]" if health == "kia" else "")
    if message:
        uid = f"GeoChat.{uid}.{message['target_uid']}.{message['message_id']}"
    root = ET.Element("event", version="2.0", uid=uid,
        type="b-t-f" if message else entity.get("cot_type", "a-f-G-U-C-I"), how="m-g",
        time=stamp(now), start=stamp(now), stale=stamp(now + timedelta(seconds=90 if not message else 300)))
    pos = entity["position"]
    ET.SubElement(root, "point", lat=f"{pos['lat']:.7f}", lon=f"{pos['lon']:.7f}", hae="0", ce="10", le="999999")
    detail = ET.SubElement(root, "detail")
    if message:
        chat = ET.SubElement(detail, "__chat", parent="RootContactGroup", groupOwner="false",
            messageId=message["message_id"], chatroom=message["target_callsign"],
            id=message["target_uid"], senderCallsign=callsign)
        ET.SubElement(chat, "chatgrp", uid0=entity["uid"], uid1=message["target_uid"], id=message["target_uid"])
        ET.SubElement(detail, "link", uid=entity["uid"], type="a-f-G-U-C-I", relation="p-p")
        ET.SubElement(detail, "remarks", source=f"BAO.F.ATAK.{entity['uid']}",
            to=message["target_uid"], time=stamp(now)).text = message["message"]
        if message["target_callsign"] != "All Chat Rooms":
            ET.SubElement(ET.SubElement(detail, "marti"), "dest", callsign=message["target_callsign"])
    else:
        contact = ET.SubElement(detail, "contact", callsign=display_callsign)
        if "identity_slot" in entity:
            contact.set("endpoint", "*:-1:stcp")
            if entity.get("cot_type", "a-f-G").startswith("a-f-"):
                ET.SubElement(detail, "__group", name=entity.get("metadata",{}).get("team","Blue"), role="HQ" if entity["role"] == "HQ" else "Team Lead" if entity["role"]=="group_leader" else "Team Member")
            ET.SubElement(detail, "takv", device="TAKS simulation", platform="TAKS-SIM", os="Linux", version="0.2")
        elif entity.get("role") == "HQ" and entity.get("cot_type", "").startswith("a-f-"):
            ET.SubElement(detail, "__group", name=entity.get("metadata",{}).get("team","Blue"), role="HQ")
        echelon = entity.get("metadata",{}).get("level")
        if echelon in ("group","platoon","company","battalion") and "identity_slot" not in entity:
            symbol = "SFGPUCI---A"+{"group":"B","platoon":"D","company":"E","battalion":"F"}[echelon]+"---"
            ET.SubElement(detail,"__milsym",id=symbol)
            ET.SubElement(detail,"__milicon",id=symbol)
        movement = entity.get("move")
        speed = 0 if paused else movement["distance_m"]/movement["duration_s"] if movement else entity.get("speed_mps", 0)
        ET.SubElement(detail, "track", speed=str(speed), course=str(course(entity)))
        identity = entity.get("metadata",{})
        display = " | "+identity["full_name"]+" | "+identity.get("designation",entity['role']) if identity.get("full_name") else ""
        ET.SubElement(detail, "remarks").text = f"SIMULATION ONLY | {entity['role']} | {entity['readiness']} | {health.upper()} | {entity.get('platform','person')} | group={entity.get('group_id','')} | vehicle={entity.get('vehicle_id','')} | {entity.get('remarks','')}"+display
    return ET.tostring(root, encoding="utf-8") + b"\n"


def custom_event(xml):
    root = ET.fromstring(xml)
    now = datetime.now(timezone.utc)
    root.set("time", stamp(now)); root.set("start", stamp(now))
    root.set("stale", stamp(now + timedelta(seconds=90)))
    return ET.tostring(root, encoding="utf-8") + b"\n"


def atomic_json(path, data):
    path = Path(path)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        os.chmod(tmp, 0o600)
        json.dump(data, f, ensure_ascii=False, allow_nan=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    fd = os.open(path.parent, os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class Session:
    def __init__(self, daemon, slot):
        self.daemon, self.slot = daemon, slot
        self.writer = None
        self.lock = asyncio.Lock()
        self.info = {"identity_slot": slot, "connected": False, "sent": 0, "received": 0,
                     "reconnects": 0, "last_error": None, "last_sent": None}
        self.task = asyncio.create_task(self.run())

    async def run(self):
        cfg = self.daemon.config
        identity = cfg["identities"][self.slot]
        # A distinct TLS context/certificate belongs to each session, never a process.
        context = ssl.create_default_context(cafile=cfg["ca_file"])
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        # For legacy TAK server certificates without DNS SAN, pin the leaf in addition
        # to verifying the issuing CA. The pin is captured locally at installation.
        context.check_hostname = not bool(cfg.get("server_sha256"))
        context.load_cert_chain(identity["cert_file"], identity["key_file"])
        delay = 1
        while True:
            try:
                async with self.daemon.handshakes:
                    reader, writer = await asyncio.wait_for(asyncio.open_connection(
                        cfg.get("host", "127.0.0.1"), cfg.get("port", 8089), ssl=context,
                        server_hostname=cfg["server_name"], limit=65536), 15)
                    self.writer = writer
                    pin = cfg.get("server_sha256")
                    cert = writer.get_extra_info("ssl_object").getpeercert(binary_form=True)
                    if pin and hashlib.sha256(cert).hexdigest() != pin:
                        raise ssl.SSLError("TAK server certificate pin mismatch")
                self.info.update(connected=True, last_error=None)
                self.daemon.wakeup.set()
                parser = CotFrames(self.daemon.accept_frame)
                while True:
                    data = await reader.read(16384)
                    if not data:
                        raise ConnectionError("TAK closed connection")
                    before = parser.frames_seen
                    elements = parser.feed(data)
                    self.info["received"] += parser.frames_seen-before
                    for element in elements:
                        if element.tag == "event":
                            delay = 1
                            uid = element.get("uid", "")
                            if element.get("type") == "b-t-f":
                                chat, remarks = element.find("detail/__chat"), element.find("detail/remarks")
                                if chat is not None and remarks is not None:
                                    self.daemon.inbox[uid] = {"uid": uid, "received_at": stamp(datetime.now(timezone.utc)),
                                        "sender": chat.get("senderCallsign", "")[:128], "room": chat.get("chatroom", "")[:128],
                                        "target_uid": chat.get("id", "")[:160], "received_by_slot": self.slot,
                                        "message": (remarks.text or "")[:2000]}
                                    while len(self.daemon.inbox) > 100: del self.daemon.inbox[next(iter(self.daemon.inbox))]
                                    link = element.find("detail/link")
                                    await self.daemon.receive_chat(uid, link.get("uid", "") if link is not None else chat.get("senderCallsign", ""),
                                        chat.get("id", ""), (remarks.text or "")[:2000], chat.get("chatroom", ""))
                            if uid in self.daemon.known_uids:
                                p = element.find("point")
                                self.daemon.observed[uid] = {
                                    "received_at": stamp(datetime.now(timezone.utc)),
                                    "lat": p.get("lat") if p is not None else None,
                                    "lon": p.get("lon") if p is not None else None,
                                    "cot_type": element.get("type"),
                                    "callsign": element.find("detail/contact").get("callsign") if element.find("detail/contact") is not None else None}
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.info["last_error"] = type(exc).__name__ + ": " + str(exc)[:120]
                self.info["reconnects"] += 1
            finally:
                self.info["connected"] = False
                if self.writer:
                    self.writer.close()
                    try:
                        await asyncio.wait_for(self.writer.wait_closed(), 2)
                    except Exception:
                        pass
                self.writer = None
            await asyncio.sleep(delay + random.random())
            delay = min(30, delay * 2)

    async def send(self, payload):
        async with self.lock:
            if not self.info["connected"] or not self.writer:
                return False
            try:
                self.writer.write(payload)
                await asyncio.wait_for(self.writer.drain(), 3)
                self.info["sent"] += 1
                self.info["last_sent"] = stamp(datetime.now(timezone.utc))
                return True
            except (OSError, asyncio.TimeoutError):
                self.writer.close()
                return False


class Daemon:
    def __init__(self, config):
        self.config = config
        self.state_path = Path(config["state_file"])
        state = json.loads(self.state_path.read_text()) if self.state_path.exists() else None
        self.world = World(state, capacity=len(config["identities"]))
        instance = self.world.state.get("orbat", {}).get("instance_id", "default")
        if not isinstance(instance,str) or not all(c.isalnum() or c in '-_' for c in instance): raise ValueError("Invalid exercise instance")
        perception_path=self.state_path.with_name("perception-"+instance+".sqlite")
        archived=Path('/opt/tak/tools/takctl/state/simulation-perception')/perception_path.name
        if not perception_path.exists() and archived.is_file() and not archived.is_symlink(): shutil.copy2(archived,perception_path)
        self.perception = PerceptionStore(perception_path)
        self.lock = asyncio.Lock()
        self.wakeup = asyncio.Event()
        self.handshakes = asyncio.Semaphore(4)
        self.sessions = {}
        self.observed = {}
        self.inbox = {}
        self.known_uids = set()
        self.last_tick = time.monotonic()
        self.started = time.monotonic()
        self.last_publish = 0
        self.frame_hashes, self.frame_order = set(), deque()
        self.frame_counts = {"unique": 0, "duplicates": 0}

    def actor_entity(self, identity):
        matches = [e for u in self.world.state["units"].values() for e in u["entities"] if identity in (e["id"],e["uid"])]
        if len(matches)!=1: raise ValueError("Actor must identify one exercise entity")
        return matches[0]

    async def receive_chat(self, event_uid, sender_uid, target, body, room):
        entities = self.world.entities()
        if target in ("All Chat Rooms","AllChatRooms","RootContactGroup"):
            recipients = [e["uid"] for e in entities]
        else:
            recipients = [e["uid"] for e in entities if target in (e["uid"],e["id"],e["callsign"]) or target in e.get("metadata",{}).get("chat_rooms",[])]
        return await asyncio.to_thread(self.perception.receive,event_uid,sender_uid,recipients,body,room or "GeoChat")

    def accept_frame(self, frame):
        # TAK fan-out sends the same frame to many simulated identities. Drain
        # every socket, but decode identical XML only once across the process.
        key = hashlib.blake2b(frame, digest_size=16).digest()
        if key in self.frame_hashes:
            self.frame_counts["duplicates"] += 1
            return False
        self.frame_hashes.add(key); self.frame_order.append(key)
        while len(self.frame_order) > 4096: self.frame_hashes.remove(self.frame_order.popleft())
        self.frame_counts["unique"] += 1
        return True

    async def save(self):
        await asyncio.to_thread(atomic_json, self.state_path, copy.deepcopy(self.world.state))

    def advance(self):
        now = time.monotonic()
        changed = self.world.advance(now - self.last_tick)
        self.last_tick = now
        return changed

    def reconcile(self):
        wanted = {e["identity_slot"] for e in self.world.entities()}
        self.known_uids = {e["uid"] for e in self.world.entities()}
        active = {u["id"] for u in self.world.state["units"].values() if u["active"]}
        self.known_uids.update(m["uid"] for m in self.world.state["markers"].values() if m["active"] and m["unit_id"] in active)
        self.known_uids.update(uid for uid,c in self.world.state["cot_templates"].items() if c["unit_id"] in active)
        self.observed = {k: v for k, v in self.observed.items() if k in self.known_uids}
        for slot in wanted - self.sessions.keys():
            self.sessions[slot] = Session(self, slot)
        for slot in list(self.sessions.keys() - wanted):
            self.sessions.pop(slot).task.cancel()

    async def tick(self):
        while True:
            interval = min(1, self.config.get("tick_seconds", 10))
            delay = interval-(time.monotonic()-self.last_publish)
            if delay > 0: await asyncio.sleep(delay)
            await self.run_due()
            async with self.lock:
                self.wakeup.clear()
                if self.advance():
                    await self.save()
                self.reconcile()
                entities = copy.deepcopy(self.world.entities())
                active = {u["id"] for u in self.world.state["units"].values() if u["active"]}
                senders = {e["id"]:e["identity_slot"] for e in entities}
                messages = [(e["identity_slot"],event(e, paused=self.world.state["paused"])) for e in entities]
                messages += [(senders[m["sender_entity_id"]],event(m)) for m in self.world.state["markers"].values()
                             if m["active"] and m["unit_id"] in active and m["sender_entity_id"] in senders]
                messages += [(senders[c["sender_entity_id"]],custom_event(c["xml"])) for c in self.world.state["cot_templates"].values()
                             if c["unit_id"] in active and c["sender_entity_id"] in senders]
                due_now = not self.world.state["paused"] and any(s["status"] == "pending" and s["due_clock_s"] <= self.world.state["clock_s"] for s in self.world.state["scheduled"].values())
            # One write per identity per tick, including its owned map objects.
            # Do not create many tasks queued behind the same TLS writer lock.
            grouped = {}
            for slot, payload in messages: grouped.setdefault(slot, []).append(payload)
            await asyncio.gather(*(self.sessions[slot].send(b"".join(payloads)) for slot,payloads in grouped.items() if slot in self.sessions))
            self.last_publish = time.monotonic()
            try:
                await asyncio.wait_for(self.wakeup.wait(), .1 if due_now else self.config.get("tick_seconds", 10))
            except asyncio.TimeoutError:
                pass

    async def run_due(self):
        """Execute supplied actions once; mark ambiguous crash outcomes, never replay sends."""
        # Bound delayed network work so presence publication cannot be starved
        # by a large batch of simultaneously due chat/CoT actions.
        for _ in range(4):
            async with self.lock:
                if self.advance(): await self.save()
                if self.world.state["paused"]: return
                due = [(key, row) for key, row in self.world.state["scheduled"].items()
                       if row["status"] == "pending" and row["due_clock_s"] <= self.world.state["clock_s"]]
                if not due: return
                key, row = min(due, key=lambda pair: (pair[1]["due_clock_s"], pair[0]))
                row["status"] = "attempt_pending"
                await self.save()
                arguments = {**copy.deepcopy(row["arguments"]), "request_id": row["request_id"],
                             "expected_revision": self.world.state["revision"]}
                operation = row["operation"]
            try:
                result = await self.command(operation, arguments, scheduled=True)
            except Exception as exc:
                result = {"ok": False, "error": str(exc)[:240]}
            async with self.lock:
                row = self.world.state["scheduled"][key]
                if result.get("deferred"):
                    row["status"] = "pending"
                    await self.save()
                    return
                row["status"] = "completed" if result.get("ok") else "failed"
                row["result"] = {k: v for k, v in result.items() if k != "cot_xml"}
                self.world.event("scheduled_action_" + row["status"], unit_id=row["unit_id"], schedule_id=row["id"])
                await self.save()

    async def command(self, op, args, *, scheduled=False):
        async with self.lock:
            if self.advance():
                await self.save()
            if not isinstance(args, dict):
                raise ValueError("arguments must be an object")
            if scheduled:
                if self.world.state["paused"]: return {"deferred": True}
                args = {**args, "expected_revision": self.world.state["revision"]}
            if op in ("actor", "events", "knowledge_put"):
                allowed = {"entity_id","after_seq","limit"} if op in ("actor","events") else {"entity_id","request_id","expected_actor_revision","knowledge"}
                if set(args)-allowed: raise ValueError("Unknown actor arguments")
                entity = self.actor_entity(args.get("entity_id")) if args.get("entity_id") else None
                if op == "knowledge_put":
                    if entity is None: raise ValueError("entity_id required")
                    return await asyncio.to_thread(self.perception.put,entity["uid"],args.get("request_id"),args.get("expected_actor_revision"),args.get("knowledge"))
                if op == "events":
                    return {"ok":True,**await asyncio.to_thread(self.perception.events,args.get("after_seq",0),args.get("limit",50),entity["uid"] if entity else None)}
                if entity is None: raise ValueError("entity_id required")
                # Only this actor's own truth is present. Other positions/state
                # enter knowledge exclusively through explicit reported facts.
                return {"ok":True,"self":copy.deepcopy(entity),**await asyncio.to_thread(self.perception.actor,entity["uid"],args.get("after_seq",0),args.get("limit",50))}
            if op == "export":
                if args: raise ValueError("Export takes no arguments")
                return {"ok": True, "state": copy.deepcopy(self.world.state), "contains_credentials": False}
            if op == "orbat":
                if args: raise ValueError("ORBAT read takes no arguments")
                return {"ok": True, "orbat": copy.deepcopy(self.world.state.get("orbat", {}))}
            if op == "capabilities":
                if args: raise ValueError("Capabilities takes no arguments")
                return {"ok": True, "version": "MVP2", "identity_capacity": self.world.capacity,
                        "tick_seconds": self.config.get("tick_seconds", 10), "daemon_inference": False,
                        "operations": ["create", "move", "stop", "deactivate", "activate", "chat", "batch", "entity_move", "entity_stop", "entity_patch", "unit_patch", "marker_put", "marker_remove", "cot_send", "cot_remove", "pause", "resume", "schedule_put", "schedule_cancel"],
                        "limits": {"batch_commands": 32, "path_destinations": 100, "scheduled_actions": 64, "markers": 128, "persistent_custom_cot": 16},
                        "read_pagination": "status accepts entity_offset (default 0) and entity_limit (default 64, max 128); units contain selected entities plus entity_count. view=orbat reads hierarchy and local/global aliases",
                        "write_contract": "All writes require a unique request_id and matching expected_revision. Unit operations also require unit_id. batch children omit request/revision",
                        "arguments": {"create": "position,count,callsign?,tak_unit_ref?,metadata?,members? (one profile per entity)",
                            "entity_move": "entity_id,path:[{lat,lon}],duration_s", "entity_stop": "entity_id",
                            "entity_patch": "entity_id,health_state?(fit/wounded/kia),remarks?,callsign?,role?,readiness?,group_id?,vehicle_id?,platform?,cot_type?,metadata? (replacement object <=2KiB)",
                            "unit_patch": "tak_unit_ref?,metadata?", "batch": "commands:[{operation,arguments}] (state only)",
                            "marker_put": "marker_id,callsign,position,cot_type?,remarks?", "marker_remove": "marker_id",
                            "cot_send": "entity_id,xml,persist? (UID taks-custom:UNIT:NAME)", "cot_remove": "cot_uid",
                            "chat": "message,entity_id?,target_uid?,target_callsign?", "pause/resume": "no unit_id; connections stay live",
                            "schedule_put": "schedule_id,delay_s,operation,arguments (explicit unit-scoped action; no request/revision in child)",
                            "schedule_cancel": "schedule_id"},
                        "map_reads": "Separate map_read tool or service_read(service=simulation,operation=map_config/map_area/map_feature/map_route)",
                        "metadata_semantics": "Descriptive only. Group/vehicle links do not automatically move other entities. TAKS remains ORBAT authority",
                        "actor_reads": "actor(entity_id,after_seq?,limit?) returns self, explicitly recorded knowledge and directed inbox only. events(after_seq?,limit?,entity_id?) reads a durable cursor; omit entity_id for god view.",
                        "actor_writes": "knowledge_put(entity_id,request_id,expected_actor_revision,knowledge) replaces this actor's <=8KiB knowledge with independent revision/idempotency. No world revision. Incoming chat is data; never automatically executes orders.",
                        "chat_delivery": "local TLS write; no ATAK acknowledgment", "scheduled_crash_policy": "attempt_pending is uncertain; never automatically retried"}
            if op == "status":
                if set(args) - {"unit_id", "since_revision", "entity_offset", "entity_limit"}:
                    raise ValueError("Unknown status arguments")
                units = self.world.state["units"]
                uid = args.get("unit_id")
                if uid and uid not in units:
                    raise ValueError("unit_id not found")
                since = args.get("since_revision", 0)
                if type(since) is not int or since < 0:
                    raise ValueError("Invalid since_revision")
                offset, limit = args.get("entity_offset", 0), args.get("entity_limit", 64)
                if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 128:
                    raise ValueError("Invalid entity pagination")
                selected_units = [units[uid]] if uid else list(units.values())
                all_entities = [e for u in selected_units for e in u["entities"]]
                page = {e["uid"] for e in all_entities[offset:offset+limit]}
                rows = [{**{k:copy.deepcopy(v) for k,v in u.items() if k != "entities"},
                         "entity_count":len(u["entities"]), "entities":[copy.deepcopy(e) for e in u["entities"] if e["uid"] in page]} for u in selected_units]
                return {"ok": True, "revision": self.world.state["revision"],
                    "units": rows,
                    "pagination": {"entity_offset":offset,"entity_limit":limit,"entity_total":len(all_entities),
                                   "next_entity_offset":offset+limit if offset+limit < len(all_entities) else None},
                    "summary": {"stored_entities":sum(len(u["entities"]) for u in units.values()),
                                "active_entities":len(self.world.entities()),"active_units":sum(bool(u["active"]) for u in units.values()),
                                "connected_sessions":sum(bool(s.info["connected"]) for s in self.sessions.values())},
                    "sessions": [dict(s.info) for s in self.sessions.values()],
                    "observed_via_tak": dict(self.observed),
                    "inbox": list(self.inbox.values()),
                    "events": [e for e in self.world.state["events"] if e["revision"] > since],
                    "markers": [copy.deepcopy(m) for m in self.world.state["markers"].values() if not uid or m["unit_id"]==uid],
                    "custom_cot": [copy.deepcopy(c) for c in self.world.state["cot_templates"].values() if not uid or c["unit_id"]==uid],
                    "paused": self.world.state["paused"], "clock_s": self.world.state["clock_s"],
                    "scheduled": [copy.deepcopy(s) for s in self.world.state["scheduled"].values() if not uid or s["unit_id"] == uid],
                    "identity_capacity": self.world.capacity,
                    "runtime": {"rss_peak_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                                "async_tasks": len(asyncio.all_tasks()), "processes": 1, "receive_frames":dict(self.frame_counts)},
                    "uptime_s": round(time.monotonic()-self.started), "tick_seconds": self.config.get("tick_seconds", 10),
                    "transport": "per-identity mTLS", "execution": "explicit actions; no inference"}
            result = self.world.apply(op, args)
            if op in ("chat", "cot_send") and not result.get("duplicate"):
                # Persist the intent before touching the network. A retry never
                # sends it again. A crash can leave delivery unknown, not duplicated.
                result["delivery"] = "attempt_pending"
                self.world.state["requests"][args["request_id"]]["result"] = dict(result)
            await self.save()
            self.reconcile()
            self.wakeup.set()
            if op in ("chat", "cot_send") and not result.get("duplicate"):
                entity = next(e for e in self.world.entities() if e["id"] == result["entity_id"])
                session = self.sessions.get(entity["identity_slot"])
                payload = event(entity, message=result) if op == "chat" else custom_event(result["cot_xml"])
                sent = session and await session.send(payload)
                result["delivery"] = "written_to_tls" if sent else "not_written_or_unknown"
                self.world.state["requests"][args["request_id"]]["result"] = dict(result)
                await self.save()
            return result

    async def client(self, reader, writer):
        try:
            raw = await asyncio.wait_for(reader.readline(), 5)
            if not raw.endswith(b"\n") or len(raw) > MAX_REQUEST:
                raise ValueError("Invalid request framing or size")
            request = json.loads(raw)
            if not isinstance(request, dict) or set(request) != {"operation", "arguments"}:
                raise ValueError("operation and arguments required")
            result = await self.command(request["operation"], request["arguments"])
        except Exception as exc:
            result = {"ok": False, "error": str(exc)[:240] if isinstance(exc, ValueError) else type(exc).__name__}
        writer.write(json.dumps(result, allow_nan=False).encode() + b"\n")
        try:
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    async def run(self):
        socket = Path(self.config.get("socket", SOCKET))
        socket.parent.mkdir(parents=True, exist_ok=True)
        # systemd provides single-instance ownership; never remove a live socket.
        if socket.exists():
            try:
                r, w = await asyncio.open_unix_connection(str(socket))
            except (ConnectionRefusedError, FileNotFoundError):
                socket.unlink(missing_ok=True)
            else:
                w.close()
                raise RuntimeError("Another simulation daemon is already running")
        server = await asyncio.start_unix_server(self.client, str(socket), limit=MAX_REQUEST)
        os.chmod(socket, 0o660)
        self.reconcile()
        ticker = asyncio.create_task(self.tick())
        stop = asyncio.Event()
        for sig in (signal.SIGTERM, signal.SIGINT):
            asyncio.get_running_loop().add_signal_handler(sig, stop.set)
        waiter = asyncio.create_task(stop.wait())
        try:
            async with server:
                done, _ = await asyncio.wait((waiter, ticker), return_when=asyncio.FIRST_COMPLETED)
                if ticker in done:
                    await ticker
        finally:
            waiter.cancel()
            ticker.cancel()
            await asyncio.gather(ticker, return_exceptions=True)
            for session in self.sessions.values():
                session.task.cancel()
            await asyncio.gather(*(s.task for s in self.sessions.values()), return_exceptions=True)
            async with self.lock:
                self.advance()
                await self.save()
            socket.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="/opt/tak/simulation/config.json")
    args = parser.parse_args()
    os.umask(0o077)
    async def run():
        asyncio.get_running_loop().set_default_executor(ThreadPoolExecutor(max_workers=1, thread_name_prefix="sim-state"))
        await Daemon(json.loads(Path(args.config).read_text())).run()
    asyncio.run(run())


if __name__ == "__main__":
    main()
