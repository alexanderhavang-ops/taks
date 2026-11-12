"""One asyncio process owns all TLS sessions and explicit exercise actions."""
from __future__ import annotations

import argparse
import asyncio
import copy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import random
import signal
import ssl
import time
import xml.etree.ElementTree as ET

from .model import World

SOCKET = "/opt/tak/simulation/control.sock"
MAX_REQUEST = 65536


def stamp(t):
    return t.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def event(entity, *, message=None):
    now = datetime.now(timezone.utc)
    uid, callsign = entity["uid"], entity["callsign"]
    if message:
        uid = f"GeoChat.{uid}.{message['target_uid']}.{message['message_id']}"
    root = ET.Element("event", version="2.0", uid=uid,
        type="b-t-f" if message else "a-f-G-U-C-I", how="m-g",
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
        ET.SubElement(detail, "contact", callsign=callsign, endpoint="*:-1:stcp")
        ET.SubElement(detail, "__group", name="Blue", role="HQ" if entity["role"] == "HQ" else "Team Member")
        ET.SubElement(detail, "takv", device="TAKS simulation", platform="TAKS-SIM", os="Linux", version="0.1")
        ET.SubElement(detail, "track", speed=str(entity.get("speed_mps", 0)), course="0")
        ET.SubElement(detail, "remarks").text = f"SIMULATION ONLY | {entity['role']} | {entity['readiness']}"
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
                delay = 1
                self.daemon.wakeup.set()
                parser = ET.XMLPullParser(events=("start", "end"))
                parser.feed("<stream>")
                root = None
                outstanding = 0
                while True:
                    data = await reader.read(16384)
                    if not data:
                        raise ConnectionError("TAK closed connection")
                    outstanding += len(data)
                    if outstanding > 1048576:
                        raise ValueError("Inbound event exceeds memory bound")
                    parser.feed(data)
                    for kind, element in parser.read_events():
                        if root is None and kind == "start":
                            root = element
                        if kind == "end" and element.tag == "event":
                            self.info["received"] += 1
                            uid = element.get("uid", "")
                            if uid in self.daemon.known_uids:
                                p = element.find("point")
                                self.daemon.observed[uid] = {
                                    "received_at": stamp(datetime.now(timezone.utc)),
                                    "lat": p.get("lat") if p is not None else None,
                                    "lon": p.get("lon") if p is not None else None}
                            element.clear()
                            outstanding = 0
                    # XMLPullParser retains completed children under root. Clearing
                    # root below keeps receive memory flat without losing partial events.
                    if root is not None:
                        root.clear()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.info["last_error"] = type(exc).__name__
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
        self.lock = asyncio.Lock()
        self.wakeup = asyncio.Event()
        self.handshakes = asyncio.Semaphore(4)
        self.sessions = {}
        self.observed = {}
        self.known_uids = set()
        self.last_tick = time.monotonic()
        self.started = time.monotonic()

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
        self.observed = {k: v for k, v in self.observed.items() if k in self.known_uids}
        for slot in wanted - self.sessions.keys():
            self.sessions[slot] = Session(self, slot)
        for slot in list(self.sessions.keys() - wanted):
            self.sessions.pop(slot).task.cancel()

    async def tick(self):
        while True:
            async with self.lock:
                self.wakeup.clear()
                if self.advance():
                    await self.save()
                self.reconcile()
                entities = copy.deepcopy(self.world.entities())
            await asyncio.gather(*(self.sessions[e["identity_slot"]].send(event(e))
                                   for e in entities if e["identity_slot"] in self.sessions))
            try:
                await asyncio.wait_for(self.wakeup.wait(), self.config.get("tick_seconds", 10))
            except asyncio.TimeoutError:
                pass

    async def command(self, op, args):
        async with self.lock:
            if self.advance():
                await self.save()
            if not isinstance(args, dict):
                raise ValueError("arguments must be an object")
            if op == "status":
                if set(args) - {"unit_id", "since_revision"}:
                    raise ValueError("Unknown status arguments")
                units = self.world.state["units"]
                uid = args.get("unit_id")
                if uid and uid not in units:
                    raise ValueError("unit_id not found")
                since = args.get("since_revision", 0)
                if type(since) is not int or since < 0:
                    raise ValueError("Invalid since_revision")
                return {"ok": True, "revision": self.world.state["revision"],
                    "units": copy.deepcopy([units[uid]] if uid else list(units.values())),
                    "sessions": [dict(s.info) for s in self.sessions.values()],
                    "observed_via_tak": dict(self.observed),
                    "events": [e for e in self.world.state["events"] if e["revision"] > since],
                    "identity_capacity": self.world.capacity,
                    "uptime_s": round(time.monotonic()-self.started), "tick_seconds": self.config.get("tick_seconds", 10),
                    "transport": "per-identity mTLS", "execution": "explicit actions; no inference"}
            result = self.world.apply(op, args)
            if op == "chat" and not result.get("duplicate"):
                # Persist the intent before touching the network. A retry never
                # sends it again. A crash can leave delivery unknown, not duplicated.
                result["delivery"] = "attempt_pending"
                self.world.state["requests"][args["request_id"]]["result"] = dict(result)
            await self.save()
            self.reconcile()
            self.wakeup.set()
            if op == "chat" and not result.get("duplicate"):
                entity = next(e for e in self.world.entities() if e["id"] == result["entity_id"])
                session = self.sessions.get(entity["identity_slot"])
                sent = session and await session.send(event(entity, message=result))
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
