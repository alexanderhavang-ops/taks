import asyncio
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
import xml.etree.ElementTree as ET

from takctl.simulation.model import World, distance
from takctl.simulation.daemon import Daemon, event
from takctl.node_language import node_language
from takctl.web.mcp_domains import map_context as maps, simulation_tools


def args(rev=0, key="create", **fields):
    return {"unit_id": "demo", "expected_revision": rev, "request_id": key, **fields}


def world():
    w = World()
    w.apply("create", args(position={"lat": 55.71, "lon": 13.21}, count=2,
        members=[{"callsign": "SIM-LEADER", "group_id": "one", "metadata": {"personality": "deliberate"}},
                 {"callsign": "SIM-VEHICLE", "platform": "vehicle", "cot_type": "a-f-G-E-V"}]))
    return w


class WorldV2Tests(unittest.TestCase):
    def test_camera_marker_and_aircraft_share_compatible_video_details(self):
        w = world()
        url = "rtsp://video.example.test:8554/exercise/camera"
        metadata = {"video_url": url, "altitude_hae_m": 120}
        w.apply("marker_put", args(1, "camera", marker_id="camera", callsign="CAMERA",
                                   position={"lat": 55.71, "lon": 13.21}, metadata=metadata))
        w.apply("entity_patch", args(2, "drone", entity_id="demo-01", platform="drone",
                                     cot_type="a-f-A-M-F-Q", metadata=metadata))
        for item in (w.state["markers"]["demo:camera"], w.entities()[0]):
            root = ET.fromstring(event(item))
            self.assertEqual(root.find("point").get("hae"), "120")
            feed = root.find("detail/__video/ConnectionEntry")
            self.assertEqual((feed.get("protocol"), feed.get("address")), ("raw", url))
        with self.assertRaises(ValueError):
            w.apply("entity_patch", args(3, "unsafe-video", entity_id="demo-01",
                                         metadata={"video_url": "rtsp://name:secret@video.example.test/stream"}))

    def test_node_language_uses_english_default_and_rereads_runtime_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            core = Path(directory) / "core.conf"
            self.assertEqual(node_language(core), "en")
            core.write_text("language = sv\n", encoding="utf-8")
            self.assertEqual(node_language(core), "sv")
            core.write_text("language = en\n", encoding="utf-8")
            self.assertEqual(node_language(core), "en")

    def test_pause_holds_each_position_clock_and_resumes_remaining_time(self):
        w = world()
        w.apply("entity_move", args(1, "walk", entity_id="demo-01", path=[{"lat": 55.711, "lon": 13.21}], duration_s=100))
        w.advance(25)
        w.apply("pause", {"expected_revision": 2, "request_id": "pause"})
        frozen = copy.deepcopy(w.state)
        self.assertFalse(w.advance(500))
        self.assertEqual(w.state, frozen)
        w.apply("resume", {"expected_revision": 3, "request_id": "resume"})
        w.advance(25)
        self.assertAlmostEqual(w.entities()[0]["move"]["elapsed_s"], 50)
        self.assertEqual(w.entities()[1]["platform"], "vehicle")

    def test_profile_validation_and_metadata_are_atomic(self):
        w = world(); before = copy.deepcopy(w.state)
        with self.assertRaises(ValueError):
            w.apply("entity_patch", args(1, "bad", entity_id="demo-01", metadata={"x": "x"*3000}, role="changed"))
        self.assertEqual(w.state, before)
        w.apply("unit_patch", args(1, "orbat", tak_unit_ref="taks-unit-ref", metadata={"readiness": "exercise"}))
        w.apply("entity_patch", args(2, "leader", entity_id="demo-01", vehicle_id="demo-02", readiness="mounted"))
        self.assertEqual(w.entities()[0]["metadata"]["personality"], "deliberate")
        self.assertEqual(w.entities()[0]["vehicle_id"], "demo-02")

    def test_timeline_cannot_target_another_unit_or_recurse(self):
        w = world()
        for operation, arguments in (("chat", {"unit_id": "other", "message": "bad"}),
                ("schedule_put", {}), ("batch", {"commands": [{"operation": "stop", "arguments": {"unit_id": "other"}}]})):
            with self.assertRaises(ValueError):
                w.apply("schedule_put", args(1, "bad", schedule_id="action", delay_s=10, operation=operation, arguments=arguments))
        result = w.apply("schedule_put", args(1, "schedule", schedule_id="action", delay_s=10, operation="chat", arguments={"unit_id": "demo", "message": "[EXERCISE] Holding"}))
        self.assertTrue(result["ok"])
        w.apply("schedule_cancel", args(2, "cancel", schedule_id="action"))
        self.assertEqual(w.state["scheduled"]["demo:action"]["status"], "cancelled")


    def test_actor_sustainment_is_explicit_persistent_and_atomic(self):
        w = World()
        w.apply("create", args(position={"lat": 55.71, "lon": 13.21}, count=1, members=[{
            "sustainment": {"health_pct": 100, "satiation_pct": 70, "hydration_pct": 80, "rations": 3,
                            "water_ml": 1500, "ammunition": {"training": 4}, "equipment": {"canteen": 1},
                            "duty_status": "on-duty", "accounted_through_clock_s": 0}}]))
        w.advance(7200)
        self.assertEqual(w.entities()[0]["sustainment"]["hydration_pct"], 80)
        w.apply("entity_patch", args(1, "meal", entity_id="demo-01", sustainment={
            "satiation_pct": 100, "rations": 2, "water_ml": 1000, "duty_status": "meal",
            "accounted_through_clock_s": 7200}))
        w = World(json.loads(json.dumps(w.state)))
        sustainment = w.entities()[0]["sustainment"]
        self.assertEqual(sustainment["ammunition"], {"training": 4})
        self.assertEqual(sustainment["equipment"], {"canteen": 1})
        self.assertEqual(sustainment["rations"], 2)
        self.assertEqual(sustainment["duty_status"], "meal")
        for invalid in ({"accounted_through_clock_s": 7199}, {"accounted_through_clock_s": 7201},
                        {"water_ml": -1}, {"ammunition": {"training": True}}):
            with self.assertRaises(ValueError):
                w.apply("entity_patch", args(2, "invalid", entity_id="demo-01", sustainment=invalid))
            self.assertEqual(w.entities()[0]["sustainment"], sustainment)
        w.apply("entity_move", args(2, "start-walk", entity_id="demo-01",
                                   path=[{"lat": 55.711, "lon": 13.21}], duration_s=100))
        w.apply("entity_patch", args(3, "fatal", entity_id="demo-01", health_state="kia",
                                    sustainment={"health_pct": 0, "satiation_pct": 0, "hydration_pct": 0}))
        self.assertEqual(w.entities()[0]["health_state"], "kia")
        self.assertEqual(w.entities()[0]["sustainment"]["health_pct"], 0)
        self.assertIsNone(w.entities()[0]["move"])


def way(uid, nodes, coords, **tags):
    return {"id": uid, "type": "way", "nodes": nodes, "geometry": [{"lat": 55.71+y, "lon": 13.21+x} for x, y in coords], "tags": {"highway": "footway", **tags}}


class MapTests(unittest.TestCase):
    def test_walking_route_goes_around_building_footprint(self):
        shortcut = way(1, [1, 2], [(0, 0), (.001, 0)])
        detour = way(2, [1, 3, 4, 2], [(0, 0), (0, .0005), (.001, .0005), (.001, 0)])
        building = way(3, [5, 6, 7, 8, 5],
                       [(.0004, -.0002), (.0006, -.0002), (.0006, .0002), (.0004, .0002), (.0004, -.0002)],
                       building="yes")
        building["tags"].pop("highway")
        route = maps.walk_route([shortcut, detour, building], shortcut["geometry"][0], shortcut["geometry"][-1])
        self.assertEqual(route["way_ids"], [2])
        self.assertEqual(route["building_footprints_checked"], 1)
        with self.assertRaisesRegex(ValueError, "No building-clear connector"):
            maps.walk_route([shortcut, detour, building], {"lat": 55.71, "lon": 13.2105}, shortcut["geometry"][-1])

    def test_raw_osm_preserves_topology_and_never_joins_missing_nodes(self):
        raw = b'<osm version="0.6"><node id="1" lat="55.71" lon="13.21"/><node id="2" lat="55.711" lon="13.21"/><way id="3"><nd ref="1"/><nd ref="2"/><tag k="highway" v="footway"/></way><way id="4"><nd ref="1"/><nd ref="99"/><tag k="highway" v="footway"/></way></osm>'
        elements = maps.osm_xml(raw)["elements"]
        self.assertEqual(elements[2]["nodes"], [1, 2])
        self.assertEqual(elements[3]["geometry"], [])
        route = maps.walk_route(elements, {"lat":55.71,"lon":13.21}, {"lat":55.711,"lon":13.21})
        self.assertEqual(route["way_ids"], [3])
        with self.assertRaises(ValueError): maps.osm_xml(b'<!DOCTYPE osm><osm/>')

    def test_bbox_api_is_fixed_and_feature_read_excludes_supporting_nodes(self):
        url = maps.bbox_url({"lat":55.71,"lon":13.21},100)
        self.assertTrue(url.startswith("https://api.openstreetmap.org/api/0.6/map?bbox="))
        data = {"elements":[{"id":1,"type":"node","lat":55.71,"lon":13.21},way(3,[1,2],[(0,0),(.001,0)])],"fetched_at":"now","osm_timestamp":None,"endpoint":"api","provider":"OpenStreetMap API 0.6"}
        with patch.object(maps,"fetch",return_value=(data,False)):
            result=maps.read("feature",{"feature_id":"way/3"})
        self.assertEqual([f["id"] for f in result["features"]],["way/3"])
        self.assertEqual(result["source"]["provider"],"OpenStreetMap API 0.6")

    def test_core_api_fetch_precedes_overpass_and_caches_complete_data(self):
        from types import SimpleNamespace
        import io
        class Response(io.BytesIO): pass
        calls=[]
        def opened(request,timeout):
            calls.append(request)
            return Response(b'<osm version="0.6"><node id="1" lat="55.71" lon="13.21"/></osm>')
        with patch.object(maps,"load_config",return_value={}), patch.object(maps.urllib.request,"build_opener",return_value=SimpleNamespace(open=opened)):
            maps.CACHE.clear()
            first,cached=maps.fetch("test", "https://api.openstreetmap.org/api/0.6/node/1")
            second,cached2=maps.fetch("test", "https://api.openstreetmap.org/api/0.6/node/1")
        self.assertFalse(cached);self.assertTrue(cached2)
        self.assertEqual(len(calls),1);self.assertEqual(calls[0].method,"GET")
        self.assertEqual(first["elements"],second["elements"])

    def test_walking_route_uses_node_topology_and_avoids_private_shortcut(self):
        elements = [way(1, [1, 2, 3], [(0, 0), (.001, 0), (.001, .001)]),
                    way(2, [1, 3], [(0, 0), (.001, .001)], access="private")]
        route = maps.walk_route(elements, {"lat": 55.71, "lon": 13.21}, {"lat": 55.711, "lon": 13.211})
        self.assertEqual(route["way_ids"], [1])
        self.assertEqual(len(route["path"]), 3)
        self.assertGreater(route["distance_m"], distance(route["path"][0], route["path"][-1]))
        disconnected = [way(1, [1, 2], [(0, 0), (.001, 0)]), way(2, [3, 4], [(.001, 0), (.001, .001)])]
        with self.assertRaisesRegex(ValueError, "No connected"):
            maps.walk_route(disconnected, {"lat": 55.71, "lon": 13.21}, {"lat": 55.711, "lon": 13.211})

    def test_map_validation_and_pagination_preserve_geometry(self):
        data = {"elements": [way(i, [1, 2], [(0, 0), (.001, 0)], name="Test path") for i in range(3)],
                "fetched_at": "now", "osm_timestamp": "source-time", "endpoint": "configured"}
        with patch.object(maps, "fetch", return_value=(data, False)):
            result = maps.read("area", {"center": {"lat": 55.71, "lon": 13.21}, "limit": 1})
            self.assertEqual(result["next_offset"], 1)
            self.assertEqual(result["features"][0]["geometry"]["coordinates"][0], [13.21, 55.71])
            self.assertEqual(result["source"]["osm_timestamp"], "source-time")
        for operation, arguments in (("area", {"center": {"lat": 0, "lon": 0}, "kinds": ["highway];evil"]}),
                                     ("feature", {"feature_id": "way/1);out;"}), ("route", {"start": {"lat": float("nan"), "lon": 0}, "end": {"lat": 0, "lon": 0}})):
            with self.assertRaises(ValueError): maps.read(operation, arguments)

    def test_no_features_means_unknown_and_relation_geometry_is_not_invented(self):
        self.assertIsNone(maps.feature({"type": "relation", "id": 1, "tags": {"building": "yes"}})["geometry"])
        with self.assertRaises(ValueError): maps.walk_route([], {"lat": 0, "lon": 0}, {"lat": 0, "lon": .001})

    def test_generic_mcp_alias_exposes_map_without_catalog_refresh(self):
        from types import SimpleNamespace
        module = SimpleNamespace(TOOLS=[], call=lambda n, a: {"old": True})
        simulation_tools.install(module)
        result = module.call("service_read", {"service": "simulation", "operation": "map_config"})
        self.assertTrue(json.loads(result["content"][0]["text"])["ok"])


class TimelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_swedish_order_keeps_literal_gate_and_localizes_acknowledgment(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state.json"
            state.write_text(json.dumps(world().state))
            daemon = Daemon({"state_file": str(state), "identities": [{}, {}]})
            daemon.reconcile = lambda: None
            actor = daemon.world.entities()[0]
            move = SimpleNamespace(action="move", direction="north", distance_m=42)
            reply = await daemon.apply_individual_order(actor, move, "sv-move", "Gå 42 meter norrut",
                                                        language="sv")
            self.assertEqual(reply, "Uppfattat. Går 42 meter norrut.")
            before = daemon.world.state["revision"]
            denied = await daemon.apply_individual_order(daemon.world.entities()[0], move, "sv-group",
                                                         "Gå hela gruppen 42 meter norrut", language="sv")
            self.assertIn("Ange avståndet", denied)
            self.assertEqual(daemon.world.state["revision"], before)

    async def test_once_only_timed_action_pause_failure_and_crash_uncertainty(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)/"state.json"; state.write_text(json.dumps(world().state))
            d = Daemon({"state_file": str(state), "identities": [{}, {}]})
            d.reconcile = lambda: None
            try:
                await d.command("schedule_put", args(1, "later", schedule_id="wound", delay_s=10, operation="entity_patch", arguments={"unit_id": "demo", "entity_id": "demo-02", "health_state": "wounded"}))
                await d.command("pause", {"expected_revision": 2, "request_id": "pause"})
                d.last_tick -= 20
                await d.run_due()
                self.assertEqual(d.world.entities()[1].get("health_state", "fit"), "fit")
                await d.command("resume", {"expected_revision": 3, "request_id": "resume"})
                d.last_tick -= 20
                await d.run_due()
                self.assertEqual(d.world.entities()[1]["health_state"], "wounded")
                revision = d.world.state["revision"]
                await d.run_due()
                self.assertEqual(d.world.state["revision"], revision)
                self.assertEqual(d.world.state["scheduled"]["demo:wound"]["status"], "completed")
                await d.command("schedule_put", args(revision, "future-walk", schedule_id="walk", delay_s=10, operation="entity_move", arguments={"unit_id": "demo", "entity_id": "demo-01", "path": [{"lat": 55.711, "lon": 13.21}], "duration_s": 100}))
                await d.command("entity_patch", args(revision+1, "injure", entity_id="demo-01", health_state="wounded"))
                d.last_tick -= 20
                await d.run_due()
                self.assertEqual(d.world.state["scheduled"]["demo:walk"]["status"], "failed")
                self.assertIsNone(d.world.entities()[0].get("move"))
                revision = d.world.state["revision"]
                await d.command("schedule_put", args(revision, "uncertain", schedule_id="uncertain", delay_s=10, operation="chat", arguments={"unit_id": "demo", "message": "Do not replay"}))
                d.world.state["scheduled"]["demo:uncertain"]["status"] = "attempt_pending"
                await d.save()
                restarted = Daemon({"state_file": str(state), "identities": [{}, {}]})
                restarted.last_tick -= 100
                await restarted.run_due()
                self.assertEqual(restarted.world.state["scheduled"]["demo:uncertain"]["status"], "attempt_pending")
            finally:
                for session in d.sessions.values(): session.task.cancel()

    async def test_recurring_chat_and_voice_keep_phase_and_skip_uncertain_sends(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state.json"
            state.write_text(json.dumps(world().state))
            (Path(tmp) / "test.wav").touch()
            cfg = {"state_file": str(state), "audio_root": tmp, "identities": [{"username": "actor", "voice_channels": ["Exercise"]},
                                  {"username": "other"}],
                   "mumble": {"enabled": True}, "xmpp": {"enabled": True, "domain": "example.test"}}
            d = Daemon(cfg)
            d.reconcile = lambda: None
            d.advance = lambda: False  # Drive the exercise clock deterministically.
            session = SimpleNamespace(send=AsyncMock(return_value=True))
            link = SimpleNamespace(info={"connected": True, "channel": "Exercise"}, ptt_task=None, ptt=AsyncMock())
            xmpp = SimpleNamespace(send_chat=AsyncMock(return_value=True))
            d.sessions[0] = session
            d.links["demo-01", "mumble"] = link
            d.links["demo-01", "xmpp"] = xmpp

            for name, operation, fields in [
                ("chat", "chat", {"message": "Exercise update"}),
                ("voice", "mumble_ptt", {"entity_id": "demo-01", "clip_id": "test"}),
                ("xmpp", "xmpp_chat", {"entity_id": "demo-01", "message": "XMPP update",
                                      "target": "other@example.test"}),
            ]:
                await d.command("schedule_put", args(
                    d.world.state["revision"], name, schedule_id=name, delay_s=10, interval_s=20,
                    operation=operation, arguments={"unit_id": "demo", **fields}))
            d.world.advance(55)
            with patch("takctl.simulation.transports.opus_clip", return_value=[b"opus"]):
                await d.run_due()
                await link.ptt_task
                await d.run_due()
            session.send.assert_awaited_once()
            link.ptt.assert_awaited_once_with([b"opus"])
            xmpp.send_chat.assert_awaited_once_with("other@example.test", "XMPP update")
            schedules = d.world.state["scheduled"]
            for row in schedules.values():
                self.assertEqual(row["last_occurrence"], {"status": "completed", "due_clock_s": 10})
                self.assertEqual(row["due_clock_s"], 70)
            chat = schedules["demo:chat"]
            interrupted = chat["request_id"]
            d.world.advance(15)
            chat["status"] = "attempt_pending"
            await d.save()

            restarted = Daemon(cfg)
            restarted.reconcile = lambda: None
            restarted.advance = lambda: False
            restarted.sessions[0] = session
            for schedule_id in ("voice", "xmpp"):
                await restarted.command("schedule_cancel", args(
                    restarted.world.state["revision"], "cancel-" + schedule_id, schedule_id=schedule_id))
            chat = restarted.world.state["scheduled"]["demo:chat"]
            self.assertEqual(chat["last_occurrence"]["status"], "uncertain")
            self.assertEqual(chat["due_clock_s"], 90)
            self.assertNotEqual(chat["request_id"], interrupted)
            await restarted.run_due()
            session.send.assert_awaited_once()
            restarted.world.advance(20)
            await restarted.run_due()
            self.assertEqual(session.send.await_count, 2)
            first, second = [ET.fromstring(call.args[0]) for call in session.send.await_args_list]
            self.assertNotEqual(first.attrib["uid"], second.attrib["uid"])

    async def test_markers_expire_while_paused_and_removal_targets_only_owned_uid(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state.json"
            state.write_text(json.dumps(world().state))
            d = Daemon({"state_file": str(state), "identities": [{}, {}]})
            d.reconcile = lambda: None
            session = SimpleNamespace(send=AsyncMock(return_value=True))
            d.sessions[0] = session
            position = {"lat": 55.71, "lon": 13.21}
            now = datetime.now(timezone.utc).timestamp()
            with patch("takctl.simulation.model.time.time", return_value=now):
                await d.command("marker_put", args(1, "put", marker_id="short", callsign="SIM-SHORT",
                                                   position=position, ttl_s=15))
                await d.command("marker_put", args(2, "put-static", marker_id="static", callsign="SIM-STATIC",
                                                   position=position, ttl_s=None))
                marker = d.world.state["markers"]["demo:short"]
                stale = datetime.fromisoformat(ET.fromstring(event(marker)).attrib["stale"]).timestamp()
                self.assertAlmostEqual(stale, now + 15, places=2)
                await d.command("pause", {"expected_revision": 3, "request_id": "pause"})
            restarted = Daemon(d.config)
            restarted.reconcile = lambda: None
            restarted.sessions[0] = session
            with patch("takctl.simulation.model.time.time", return_value=now + 16):
                await restarted.run_due()
                revision = restarted.world.state["revision"]
                self.assertEqual(list(json.loads(state.read_text())["markers"]), ["demo:static"])
                await restarted.command("marker_remove", args(revision, "remove", marker_id="static"))
                await restarted.command("marker_remove", args(revision, "remove", marker_id="static"))
            session.send.assert_awaited_once()
            removal = ET.fromstring(session.send.await_args.args[0])
            self.assertEqual(removal.attrib["type"], "t-x-d-d")
            self.assertEqual(removal.find("detail/link").attrib["uid"], "taks-marker:demo:static")
            self.assertIsNotNone(removal.find("detail/__forcedelete"))
            self.assertEqual(json.loads(state.read_text())["markers"], {})

    async def test_scheduled_marker_add_and_remove_can_be_registered_before_marker_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state.json"
            state.write_text(json.dumps(world().state))
            d = Daemon({"state_file": str(state), "identities": [{}, {}]})
            d.reconcile = lambda: None
            d.advance = lambda: False
            specs = [("add", "marker_put", 10, {"callsign": "SIM-CYCLE", "ttl_s": 15,
                                                "position": {"lat": 55.71, "lon": 13.21}}),
                     ("remove", "marker_remove", 20, {})]
            for key, operation, delay, extra in specs:
                await d.command("schedule_put", args(
                    d.world.state["revision"], key, schedule_id=key, operation=operation,
                    delay_s=delay, interval_s=20, arguments={"unit_id": "demo", "marker_id": "cycle", **extra}))
            for _ in range(3):
                d.world.advance(10)
                await d.run_due()
                self.assertEqual(len(d.world.state["markers"]), 1)
                d.world.advance(10)
                await d.run_due()
                self.assertEqual(d.world.state["markers"], {})


    async def test_unattended_orders_reply_to_the_operator_on_the_originating_transport(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state.json"
            state.write_text(json.dumps(world().state))
            d = Daemon({"state_file": str(state), "identities": [{}, {}],
                        "orders": {"model": "fixture", "xmpp_senders": ["operator@example.test"],
                                   "geochat_senders": ["operator-uid"]}})
            d.reconcile = lambda: None
            await d.command("entity_patch", args(1, "food", entity_id="demo-01",
                                                 sustainment={"rations": 2, "satiation_pct": 50}))
            session = SimpleNamespace(send=AsyncMock(return_value=True))
            xmpp = SimpleNamespace(send_chat=AsyncMock(return_value=True))
            d.sessions[0] = session
            d.links["demo-02", "xmpp"] = xmpp
            actor, second = d.world.entities()
            await d.receive_chat("fake", "unlisted", actor["uid"], "Move 100m north", actor["callsign"],
                                 sender_callsign="OPERATOR")
            await d.receive_chat("broadcast", "operator-uid", "All Chat Rooms", "Move 100m north",
                                 "All Chat Rooms", sender_callsign="OPERATOR")
            self.assertTrue(d.orders.empty())
            await d.receive_chat("move", "operator-uid", actor["uid"], "Move 100m north", actor["callsign"],
                                 sender_callsign="OPERATOR")
            await d.receive_chat("move", "operator-uid", actor["uid"], "Move 100m north", actor["callsign"],
                                 sender_callsign="OPERATOR")
            d.queue_order("xmpp", second, "food-2", "operator@example.test", "Go grab some food")
            move = SimpleNamespace(action="move", direction="north", distance_m=100)
            food = SimpleNamespace(action="eat", direction="none", distance_m=0)
            with patch("takctl.simulation.daemon.interpret_individual_order", side_effect=[move, food]) as interpret:
                worker = asyncio.create_task(d.run_orders())
                try:
                    for _ in range(100):
                        if interpret.await_count == 2:
                            break
                        await asyncio.sleep(.01)
                    self.assertEqual(interpret.await_count, 2)
                    for _ in range(100):
                        if session.send.await_count and xmpp.send_chat.await_count:
                            break
                        await asyncio.sleep(.01)
                finally:
                    worker.cancel()
                    await asyncio.gather(worker, return_exceptions=True)
            self.assertEqual(d.world.entities()[0]["move"]["duration_s"], 100)
            self.assertIsNone(d.world.entities()[1].get("move"))
            reply = ET.fromstring(session.send.await_args.args[0])
            self.assertIn("Moving 100 metres north", reply.find("detail/remarks").text)
            self.assertEqual(reply.find("detail/__chat").attrib["id"], "operator-uid")
            xmpp.send_chat.assert_awaited_once_with("operator@example.test", "Unable. I don't have a ration left.")
            rejected = await d.apply_individual_order(d.world.entities()[1], move, "bad-order",
                                                      "Move everyone 100 m north")
            self.assertTrue(rejected.startswith("Unable"))
            text = await d.apply_individual_order(d.world.entities()[0], food, "ration-order", "Go grab some food")
            self.assertIn("eaten", text)
            self.assertEqual(d.world.entities()[0]["sustainment"]["rations"], 1)


    async def test_leader_chat_uses_real_appointment_and_a_present_follow_track(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state.json"
            state.write_text(json.dumps(world().state))
            d = Daemon({"state_file": str(state), "identities": [{}, {}],
                        "orders": {"model": "fixture", "xmpp_senders": ["operator@example.test"],
                                   "geochat_senders": ["operator-uid"]}})
            d.reconcile = lambda: None
            leader, member = d.world.entities()
            shape = SimpleNamespace(action="formation", echelon=None, formation="line", target=None)
            wrong = await d.apply_leader_order(member, shape, "order-wrong", "Form a line",
                                               "xmpp", "operator@example.test")
            self.assertIn("don't command", wrong)
            reply = await d.apply_leader_order(leader, shape, "order-shape", "Form a line",
                                               "xmpp", "operator@example.test")
            self.assertEqual(reply, "Roger. Forming up.")
            follow = SimpleNamespace(action="follow", echelon=None, formation="two_columns", target="me")
            leader = d.world.entities()[0]
            body = "Follow me in two columns"
            stale = await d.apply_leader_order(leader, follow, "order-stale", body,
                                               "xmpp", "operator@example.test")
            self.assertIn("current position", stale)
            d.operator_tracks["operator-uid"] = (datetime.now(timezone.utc), {"lat": 55.711, "lon": 13.21})
            reply = await d.apply_leader_order(leader, follow, "order-follow", body,
                                               "xmpp", "operator@example.test")
            self.assertEqual(reply, "Roger. Following.")
            unit = d.world.state["units"]["demo"]
            self.assertEqual(unit["formation"], "two_columns")
            self.assertEqual(unit["exercise_motion"]["target"], "operator-uid")


if __name__ == "__main__": unittest.main()
