import asyncio
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from takctl.simulation.model import World, distance
from takctl.simulation.daemon import Daemon
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


def way(uid, nodes, coords, **tags):
    return {"id": uid, "type": "way", "nodes": nodes, "geometry": [{"lat": 55.71+y, "lon": 13.21+x} for x, y in coords], "tags": {"highway": "footway", **tags}}


class MapTests(unittest.TestCase):
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


if __name__ == "__main__": unittest.main()
