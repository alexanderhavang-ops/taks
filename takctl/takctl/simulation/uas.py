"""A point-to-point MAVLink adapter for a configured SimKeeper aircraft."""

import argparse
import ipaddress
import json
from pathlib import Path
import socket
import time
import uuid

from .model import distance, point
from takctl.web.mcp_domains.simulation_tools import simulation


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

    def read(self):
        status = self.call("uas_status", {"entity_id": self.entity}, timeout=2)
        return status["actor"] if status.get("ok") else None

    def move(self, position=None):
        if position is not None:
            position = point(position)
            if distance(position, self.center) > self.radius:
                return False
        result = self.call("uas_move", {
            "entity_id": self.entity, "unit_id": self.unit, "position": position,
            "request_id": "uas-" + uuid.uuid4().hex,
        }, timeout=3)
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

    def video_info(self):
        m = self.ids
        self.sender.video_stream_information_send(
            1, 1, m.VIDEO_STREAM_TYPE_RTSP, m.VIDEO_STREAM_STATUS_FLAGS_RUNNING,
            5, 320, 180, 0, 0, 65, b"SimKeeper", self.video.encode()[:160],
        )

    def receive(self, message):
        m = self.ids
        if message.get_type() not in ("COMMAND_INT", "COMMAND_LONG"):
            return
        if (message.get_srcSystem() != self.controller_id or message.target_system != self.system_id
                or message.target_component not in (0, 1)):
            return
        command = message.command
        result = m.MAV_RESULT_UNSUPPORTED
        if command == m.MAV_CMD_DO_REPOSITION and message.get_type() == "COMMAND_INT":
            if message.frame in (m.MAV_FRAME_GLOBAL, m.MAV_FRAME_GLOBAL_INT,
                                 m.MAV_FRAME_GLOBAL_RELATIVE_ALT, m.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT):
                position = {"lat": message.x / 1e7, "lon": message.y / 1e7}
                try:
                    result = m.MAV_RESULT_ACCEPTED if self.aircraft.move(position) else m.MAV_RESULT_DENIED
                except ValueError:
                    result = m.MAV_RESULT_DENIED
        elif (command == m.MAV_CMD_NAV_LOITER_UNLIM
              or (command == m.MAV_CMD_DO_PAUSE_CONTINUE and message.param1 == 0)):
            result = m.MAV_RESULT_ACCEPTED if self.aircraft.move() else m.MAV_RESULT_DENIED
        elif (command == m.MAV_CMD_REQUEST_MESSAGE
              and message.param1 == m.MAVLINK_MSG_ID_VIDEO_STREAM_INFORMATION and self.video):
            self.video_info()
            result = m.MAV_RESULT_ACCEPTED
        self.sender.command_ack_send(command, result, 0, 0, self.controller_id, message.get_srcComponent())


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
    actor = None
    while True:
        try:
            now = time.monotonic()
            if now >= due:
                actor = aircraft.read()
                if actor:
                    wire.telemetry(actor)
                due = now + 1
            data = link.sock.recv(4096)
            if not actor:
                continue
            for message in wire.sender.parse_buffer(data) or ():
                wire.receive(message)
        except (socket.timeout, ConnectionRefusedError):
            continue


if __name__ == "__main__":
    main()
