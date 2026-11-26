"""A point-to-point MAVLink adapter for a configured SimKeeper aircraft."""

import argparse
from collections import Counter, deque
import ipaddress
import json
import logging
from pathlib import Path
import socket
import time
import uuid

from .model import distance, point
from takctl.web.mcp_domains.simulation_tools import UAS_DIAGNOSTICS, simulation


class Diagnostics:
    def __init__(self, config):
        self.started_at = time.time()
        self.config = {
            "entity_id": config.get("entity_id"),
            "system_id": int(config.get("system_id", 1)),
            "controller_system_id": int(config.get("controller_system_id", 255)),
            "video_configured": bool(config.get("video_url")),
        }
        self.counts = Counter()
        self.last_seen = {}
        self.commands = deque(maxlen=24)
        self.control_frames = {}
        self.actor = None

    def record(self, event):
        self.counts[event] += 1
        self.last_seen[event] = time.time()

    def publish(self, path):
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps({
            "started_at": self.started_at, "updated_at": time.time(), "config": self.config,
            "counts": self.counts, "last_seen": self.last_seen, "actor": self.actor,
            "commands": list(self.commands), "last_unhandled_control_frames": self.control_frames,
        }, allow_nan=False))
        temporary.replace(path)


class Aircraft:
    def __init__(self, config, call=simulation):
        self.call = call
        self.unit = config["unit_id"]
        self.entity = config["entity_id"]
        self.center = point(config["center"])
        self.radius = float(config.get("radius_m", 500))
        if not 50 <= self.radius <= 2000:
            raise ValueError("Exercise flight radius must be 50–2000 metres")
        self.ground = float(config["ground_hae_m"])
        self.status_error = None
        self.move_error = None

    def read(self):
        status = self.call("uas_status", {"entity_id": self.entity}, timeout=2)
        self.status_error = None if status.get("ok") else str(status.get("error", "Aircraft status unavailable"))[:160]
        return status["actor"] if status.get("ok") else None

    def move(self, position=None):
        self.move_error = None
        if position is not None:
            position = point(position)
            if distance(position, self.center) > self.radius:
                self.move_error = "Destination outside the exercise area"
                return False
        result = self.call("uas_move", {
            "entity_id": self.entity, "unit_id": self.unit, "position": position,
            "request_id": "uas-" + uuid.uuid4().hex,
        }, timeout=3)
        if not result.get("ok"):
            self.move_error = str(result.get("error", "Simulator rejected move"))[:160]
        return bool(result.get("ok"))


class Wire:
    def __init__(self, transport, mav, aircraft, config):
        self.transport = transport
        self.ids = mav
        self.aircraft = aircraft
        self.system_id = int(config.get("system_id", 1))
        self.controller_id = int(config.get("controller_system_id", 255))
        self.sender = mav.MAVLink(transport, srcSystem=self.system_id, srcComponent=1)
        self.sender.robust_parsing = True
        self.video = config.get("video_url", "")
        self.started = time.monotonic()
        self.diagnostics = Diagnostics(config)

    def telemetry(self, actor):
        m, link = self.ids, self.sender
        pc = actor["position"]
        hae = actor["metadata"]["altitude_hae_m"]
        # GLOBAL_POSITION_INT reports AMSL rather than ellipsoid height.
        amsl = hae - float(actor["metadata"].get("geoid_offset_m", 0))
        link.heartbeat_send(m.MAV_TYPE_QUADROTOR, m.MAV_AUTOPILOT_ARDUPILOTMEGA,
                            m.MAV_MODE_FLAG_GUIDED_ENABLED | m.MAV_MODE_FLAG_SAFETY_ARMED, 4, m.MAV_STATE_ACTIVE)
        link.global_position_int_send(int((time.monotonic() - self.started) * 1000) % 2**32,
                                      round(pc["lat"] * 1e7), round(pc["lon"] * 1e7),
                                      round(amsl * 1000), round((hae - self.aircraft.ground) * 1000),
                                      0, 0, 0, 65535)
        self.diagnostics.record("position_telemetry_sent")

    def video_info(self):
        m = self.ids
        self.sender.video_stream_information_send(
            1, 1, m.VIDEO_STREAM_TYPE_RTSP, m.VIDEO_STREAM_STATUS_FLAGS_RUNNING,
            5, 320, 180, 0, 0, 65, b"SimKeeper", self.video.encode()[:160],
        )
        self.diagnostics.record("video_stream_information_sent")

    def receive(self, message, *, aircraft_available=True):
        m = self.ids
        kind = message.get_type()
        self.diagnostics.record("bad_data" if kind == "BAD_DATA" else "parsed_messages")
        if kind == "HEARTBEAT":
            self.diagnostics.record("heartbeat_received")
        if kind not in ("COMMAND_INT", "COMMAND_LONG"):
            if kind in ("SET_POSITION_TARGET_LOCAL_NED",
                        "SET_POSITION_TARGET_GLOBAL_INT", "MISSION_ITEM", "MISSION_ITEM_INT"):
                self.diagnostics.record(kind)
                self.diagnostics.control_frames[kind] = {
                    "at": self.diagnostics.last_seen[kind],
                    "source_system": message.get_srcSystem(),
                    "target_system": message.target_system,
                }
            return
        command = message.command
        event = {
            "at": time.time(), "message": kind, "command": command,
            "source_system": message.get_srcSystem(), "source_component": message.get_srcComponent(),
            "target_system": message.target_system, "target_component": message.target_component,
            "ack_sent": False,
        }
        if kind == "COMMAND_INT":
            event["frame"] = message.frame
        if command == m.MAV_CMD_REQUEST_MESSAGE and 0 <= message.param1 <= 0xFFFFFF:
            event["requested_message_id"] = int(message.param1)
        self.diagnostics.commands.append(event)
        self.diagnostics.record("commands_received")
        if event["source_system"] != self.controller_id:
            event["reason"] = "unexpected_controller_system"
            return
        if message.target_system != self.system_id or message.target_component not in (0, 1):
            event["reason"] = "wrong_target"
            return
        if not aircraft_available:
            event["reason"] = "aircraft_unavailable"
            return
        result = m.MAV_RESULT_UNSUPPORTED
        event["reason"] = "unsupported_command"
        if command == m.MAV_CMD_DO_REPOSITION and kind == "COMMAND_INT":
            event["reason"] = "unsupported_coordinate_frame"
            if message.frame in (m.MAV_FRAME_GLOBAL, m.MAV_FRAME_GLOBAL_INT,
                                 m.MAV_FRAME_GLOBAL_RELATIVE_ALT, m.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT):
                position = {"lat": message.x / 1e7, "lon": message.y / 1e7}
                try:
                    result = m.MAV_RESULT_ACCEPTED if self.aircraft.move(position) else m.MAV_RESULT_DENIED
                    event["reason"] = "move_applied" if result == m.MAV_RESULT_ACCEPTED else self.aircraft.move_error
                except ValueError as exc:
                    result = m.MAV_RESULT_DENIED
                    event["reason"] = str(exc)[:160]
        elif command == m.MAV_CMD_DO_REPOSITION:
            event["reason"] = "unsupported_command_format"
        elif (command == m.MAV_CMD_NAV_LOITER_UNLIM
              or (command == m.MAV_CMD_DO_PAUSE_CONTINUE and message.param1 == 0)):
            result = m.MAV_RESULT_ACCEPTED if self.aircraft.move() else m.MAV_RESULT_DENIED
            event["reason"] = "hold_applied" if result == m.MAV_RESULT_ACCEPTED else self.aircraft.move_error
        elif command == m.MAV_CMD_REQUEST_MESSAGE and message.param1 == m.MAVLINK_MSG_ID_VIDEO_STREAM_INFORMATION:
            event["reason"] = "video_uri_not_configured"
            if self.video:
                event["reason"] = "video_announcement_pending"
                self.video_info()
                event["reason"] = "video_announced"
                result = m.MAV_RESULT_ACCEPTED
        event["ack_result"] = result
        self.sender.command_ack_send(command, result, 0, 0, self.controller_id, message.get_srcComponent())
        event["ack_sent"] = True


class Datagram:
    def __init__(self, config):
        peer = ipaddress.IPv4Address(config["controller_address"])
        networks = tuple(map(ipaddress.IPv4Network, ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8")))
        if not any(peer in network for network in networks):
            raise ValueError("Use a private exercise-network controller address")
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((config["bind_address"], int(config.get("bind_port", 14550))))
        self.sock.connect((str(peer), int(config.get("controller_port", 14550))))
        self.sock.settimeout(.25)

    def write(self, payload):
        return self.sock.send(payload)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    config = json.loads(parser.parse_args().config.read_text())
    from pymavlink.dialects.v20 import common

    link = Datagram(config)
    aircraft = Aircraft(config)
    wire = Wire(link, common, aircraft, config)
    due = 0
    publish_due = 0
    publish_failed = False
    actor = None
    while True:
        now = time.monotonic()
        if now >= publish_due:
            publish_due = now + 2
            try:
                wire.diagnostics.publish(UAS_DIAGNOSTICS)
                publish_failed = False
            except OSError:
                if not publish_failed:
                    logging.exception("Unable to publish UAS diagnostics")
                publish_failed = True
        try:
            if now >= due:
                due = now + 1
                actor = aircraft.read()
                wire.diagnostics.actor = (
                    {"available": True, "position": actor["position"], "moving": bool(actor.get("move"))}
                    if actor else {"available": False, "reason": aircraft.status_error}
                )
                if actor:
                    wire.telemetry(actor)
            data = link.sock.recv(4096)
            wire.diagnostics.record("datagrams_received")
            for message in wire.sender.parse_buffer(data) or ():
                wire.receive(message, aircraft_available=actor is not None)
        except socket.timeout:
            continue
        except ConnectionRefusedError:
            wire.diagnostics.record("udp_connection_refused")
            continue


if __name__ == "__main__":
    main()
