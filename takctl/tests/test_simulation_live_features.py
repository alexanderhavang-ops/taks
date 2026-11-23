import asyncio
import hashlib
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch
from xml.etree import ElementTree

from takctl.simulation.daemon import Daemon
from takctl.simulation.model import World
from takctl.simulation.speech import spoken_target, voice_identity
from takctl.simulation.uas import Aircraft, Wire


def exercise(directory, **config):
    world = World()
    world.apply("create", {
        "unit_id": "demo", "request_id": "new", "expected_revision": 0, "count": 2,
        "position": {"lat": 55.71, "lon": 13.21},
        "members": [
            {"callsign": "ALPHA-1", "sustainment": {"rations": 2}},
            {"callsign": "EYE-1", "cot_type": "a-f-A-M-F-Q", "platform": "drone",
             "metadata": {"altitude_hae_m": 100}},
        ],
    })
    path = Path(directory) / "world.json"
    path.write_text(json.dumps(world.state))
    daemon = Daemon({"state_file": str(path), "identities": [{}, {}], **config})
    daemon.reconcile = lambda: None
    return daemon


class SpeechTests(unittest.IsolatedAsyncioTestCase):
    async def test_vx_identity_and_channel_gate_then_direct_text_and_spoken_reply(self):
        with tempfile.TemporaryDirectory() as directory:
            daemon = exercise(directory, orders={"model": "fixture", "mumble_senders": ["phone-uid"],
                                                  "mumble_voice_replies": True}, mumble={"enabled": True})
            actor = daemon.world.entities()[0]
            link = SimpleNamespace(info={"connected": True, "channel": "exercise"}, ptt_task=None, ptt=AsyncMock())
            daemon.config["identities"][0] = {"voice_channels": ["exercise"]}
            daemon.links[(actor["id"], "mumble")] = link
            session = AsyncMock()
            daemon.sessions[0] = session
            speaker = "OPERATOR---vx-session"
            digest = hashlib.sha256(f"OPERATOR|phone-uid|{speaker}".encode()).digest()
            registered = 100000 + int.from_bytes(digest[:4], "big") % 2000000000
            fields = {"segment_id": "new-burst", "speaker": speaker, "user_id": registered,
                      "text": "Alpha 1, eat a ration", "channel": "exercise"}
            self.assertIsNone(voice_identity(speaker, 2100000000, ["phone-uid"]))
            self.assertIsNone(spoken_target("everyone, eat", [actor]))
            self.assertFalse(daemon.voice_order({**fields, "channel": "another"})["queued"])
            self.assertFalse(daemon.voice_order({**fields, "user_id": 55})["queued"])
            self.assertTrue((await daemon.command("voice_order", fields))["queued"])
            self.assertFalse(daemon.voice_order(fields)["queued"])
            with (patch("takctl.simulation.daemon.interpret_individual_order",
                        return_value=SimpleNamespace(action="eat")),
                  patch("takctl.simulation.speech.speech_frames", return_value=[b"opus"])):
                worker = asyncio.create_task(daemon.run_orders())
                try:
                    async with asyncio.timeout(3):
                        while link.ptt_task is None or not link.ptt_task.done():
                            await asyncio.sleep(.01)
                finally:
                    worker.cancel()
                    await asyncio.gather(worker, return_exceptions=True)
            self.assertEqual(daemon.world.entities()[0]["sustainment"]["rations"], 1)
            reply = ElementTree.fromstring(session.send.await_args.args[0])
            self.assertEqual(reply.find("detail/__chat").get("id"), "phone-uid")
            self.assertIn("eaten a ration", reply.find("detail/remarks").text)
            link.ptt.assert_awaited_once_with([b"opus"], channel="exercise")


class CameraAndUASTests(unittest.IsolatedAsyncioTestCase):
    async def test_fixed_and_drone_feed_publication_and_aircraft_reposition(self):
        with tempfile.TemporaryDirectory() as directory:
            center = {"lat": 55.71, "lon": 13.21}
            daemon = exercise(directory, uas={"entity_id": "demo-02", "unit_id": "demo",
                                             "center": center, "radius_m": 500})
            aircraft = (await daemon.command("uas_status", {"entity_id": "demo-02"}))["actor"]
            daemon.config["cameras"] = {
                "pole": {"unit_id": "demo", "position": center, "hae_m": 18,
                         "video_url": "rtsp://example.test/exercise/pole"},
                "eye": {"aircraft_uid": aircraft["uid"], "video_url": "rtsp://example.test/exercise/eye"},
            }
            fixed, moving = daemon.camera_events(daemon.world.entities(), {"demo": 0})
            self.assertEqual(moving[aircraft["uid"]], "rtsp://example.test/exercise/eye")
            marker = ElementTree.fromstring(fixed[0][1])
            self.assertEqual(marker.find("detail/__video/ConnectionEntry").get("address"),
                             "rtsp://example.test/exercise/pole")
            fields = {"unit_id": "demo", "entity_id": "demo-02", "request_id": "move-uas"}
            with self.assertRaisesRegex(ValueError, "outside"):
                await daemon.command("uas_move", {**fields, "position": {"lat": 56.71, "lon": 13.21}})
            target = {"lat": 55.7109, "lon": 13.21}
            self.assertTrue((await daemon.command("uas_move", {**fields, "position": target}))["ok"])
            drone = daemon.world.entities()[1]
            self.assertEqual(drone["move"]["path"][-1], target)
            self.assertEqual(drone["metadata"]["altitude_hae_m"], 100)
            await daemon.command("uas_move", {**fields, "request_id": "hold", "position": None})
            self.assertIsNone(daemon.world.entities()[1]["move"])

    async def test_ground_routes_reject_crossings_aircraft_remains_free_to_overfly(self):
        with tempfile.TemporaryDirectory() as directory:
            ring = [{"lon": lon, "lat": lat} for lon, lat in
                    [(13.2102, 55.7099), (13.2104, 55.7099), (13.2104, 55.7101),
                     (13.2102, 55.7101), (13.2102, 55.7099)]]
            daemon = exercise(directory, ground_buildings=[{"tags": {"building": "yes"}, "geometry": ring}])
            fields = {"unit_id": "demo", "entity_id": "demo-01", "request_id": "cross",
                      "expected_revision": 1, "duration_s": 60, "path": [{"lat": 55.71, "lon": 13.2106}]}
            with self.assertRaisesRegex(ValueError, "mapped building"):
                await daemon.command("entity_move", fields)
            self.assertTrue((await daemon.command("entity_move", {**fields, "entity_id": "demo-02"}))["ok"])

    def test_media_config_limits_viewers_and_resolves_fixed_and_moving_urls(self):
        script = Path(__file__).resolve().parents[2] / "tools/install-simulation-media.py"
        spec = spec_from_file_location("install_simulation_media", script)
        module = module_from_spec(spec)
        spec.loader.exec_module(module)
        scene = {"cameras": {"pole": {}, "eye": {"aircraft_uid": "u-1"}}}
        config, urls = module.manifest(scene, ["10.20.0.0/24"], "taklabs.example.test")
        self.assertEqual(set(config["paths"]), {"exercise/pole", "exercise/eye"})
        self.assertEqual(config["authInternalUsers"][0]["ips"], ["127.0.0.1/32"])
        self.assertEqual(config["authInternalUsers"][1]["ips"], ["10.20.0.0/24"])
        self.assertEqual(urls["eye"], "rtsp://taklabs.example.test:8554/exercise/eye")
        with self.assertRaises(ValueError):
            module.manifest(scene, ["0.0.0.0/0"], "taklabs.example.test")

    def test_uas_bridge_forwards_only_the_selected_aircraft_operation(self):
        calls = []
        def call(op, args, *, timeout):
            calls.append((op, args))
            return {"ok": True}

        config = {"entity_id": "demo-02", "unit_id": "demo", "center": {"lat": 55.71, "lon": 13.21},
                  "radius_m": 500, "ground_hae_m": 20}
        actor = Aircraft(config, call)
        self.assertFalse(actor.move({"lat": 55.80, "lon": 13.21}))
        self.assertTrue(actor.move({"lat": 55.7101, "lon": 13.21}))
        self.assertEqual(calls[0][0], "uas_move")
        self.assertEqual(calls[0][1]["entity_id"], "demo-02")

    def test_uas_wire_targets_only_the_named_controller_and_command_subset(self):
        sender = Mock()
        dialect = SimpleNamespace(
            MAVLink=Mock(return_value=sender), MAV_CMD_DO_REPOSITION=192, MAV_CMD_NAV_LOITER_UNLIM=17,
            MAV_CMD_DO_PAUSE_CONTINUE=193, MAV_CMD_REQUEST_MESSAGE=512, MAV_RESULT_UNSUPPORTED=3,
            MAV_RESULT_ACCEPTED=0, MAV_RESULT_DENIED=2, MAV_FRAME_GLOBAL=0, MAV_FRAME_GLOBAL_INT=5,
            MAV_FRAME_GLOBAL_RELATIVE_ALT=3, MAV_FRAME_GLOBAL_RELATIVE_ALT_INT=6,
        )
        aircraft = Mock()
        aircraft.move.return_value = True
        link = Wire(Mock(), dialect, aircraft, {"system_id": 17, "controller_system_id": 255})
        fields = {"target_system": 17, "target_component": 1, "command": 192, "frame": 5,
                  "x": 557100000, "y": 132100000, "param1": 0,
                  "get_type": lambda: "COMMAND_INT", "get_srcComponent": lambda: 190}
        link.receive(SimpleNamespace(**fields, get_srcSystem=lambda: 254))
        aircraft.move.assert_not_called()
        link.receive(SimpleNamespace(**fields, get_srcSystem=lambda: 255))
        aircraft.move.assert_called_once_with({"lat": 55.71, "lon": 13.21})
        sender.command_ack_send.assert_called_once_with(192, 0, 0, 0, 255, 190)
