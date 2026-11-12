import asyncio
import copy
import json
from pathlib import Path
import ssl
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from takctl.simulation.model import World, distance
from takctl.simulation.daemon import Daemon, event
from takctl.web.mcp_domains import simulation_tools as tools


def args(revision=0, request_id="create", **fields):
    return {"unit_id": "demo", "request_id": request_id, "expected_revision": revision, **fields}


def created():
    w = World(capacity=8)
    w.apply("create", args(position={"lat": 55.71, "lon": 13.21}, count=4))
    return w


class WorldTests(unittest.TestCase):
    def test_movement_progresses_group_and_stops(self):
        w = created()
        start = copy.deepcopy(w.state["units"]["demo"])
        end = {"lat": 55.713, "lon": 13.21}
        w.apply("move", args(1, "move", path=[end], duration_s=100))
        self.assertEqual(w.state["units"]["demo"]["position"], start["position"])
        w.advance(50)
        u = w.state["units"]["demo"]
        self.assertAlmostEqual(distance(start["position"], u["position"]), distance(start["position"], end)/2, places=2)
        for before, after in zip(start["entities"], u["entities"]):
            self.assertGreater(distance(before["position"], after["position"]), 150)
        frozen = copy.deepcopy(u["position"])
        w.apply("stop", args(2, "stop"))
        w.advance(1000)
        self.assertEqual(w.state["units"]["demo"]["position"], frozen)

    def test_waypoint_corner_and_restart_preserve_progress(self):
        w = created()
        path = [{"lat":55.711,"lon":13.21}, {"lat":55.711,"lon":13.212}]
        w.apply("move", args(1, "move", path=path, duration_s=100))
        w.advance(25)
        restored = World(json.loads(json.dumps(w.state)), capacity=8)
        self.assertEqual(restored.state, w.state)
        restored.advance(75)
        self.assertIsNone(restored.state["units"]["demo"]["move"])
        self.assertLess(distance(restored.state["units"]["demo"]["position"], path[-1]), .01)

    def test_retry_and_conflict(self):
        w = created()
        request = args(1, "move", path=[{"lat":55.711,"lon":13.21}], duration_s=100)
        first = w.apply("move", request)
        self.assertTrue(w.apply("move", request)["duplicate"])
        self.assertEqual(w.state["revision"], 2)
        with self.assertRaises(ValueError):
            w.apply("move", {**request, "duration_s": 200})
        with self.assertRaises(ValueError):
            w.apply("stop", args(1, "stale"))
        self.assertEqual(first["action_id"], w.state["units"]["demo"]["move"]["id"])

    def test_bad_path_atomic_and_nan_rejected(self):
        w = created()
        before = copy.deepcopy(w.state)
        for p in ({"lat":90,"lon":13}, {"lat":float("nan"),"lon":13}, {"lat":55}):
            with self.assertRaises(ValueError):
                w.apply("move", args(1, "bad", path=[p], duration_s=10))
            self.assertEqual(before, w.state)

    def test_unique_slots_capacity_and_deactivation(self):
        w = created()
        a = args(1, "second", unit_id="other", position={"lat":55.71,"lon":13.21}, count=4)
        w.apply("create", a)
        self.assertEqual(len({e["identity_slot"] for e in w.entities()}), 8)
        with self.assertRaises(ValueError):
            w.apply("create", args(2,"overflow",unit_id="full",position={"lat":55.71,"lon":13.21},count=1))
        w.apply("deactivate", args(2,"remove"))
        w.apply("create", args(3,"reused",unit_id="new",position={"lat":55.71,"lon":13.21},count=4))
        self.assertEqual(len({e["identity_slot"] for e in w.entities()}), 8)

    def test_cot_safe_xml_and_coordinates(self):
        e = created().entities()[0]
        e["callsign"] = 'SIM-"<&'
        parsed = ET.fromstring(event(e))
        self.assertEqual(parsed.find("detail/contact").get("callsign"), e["callsign"])
        self.assertAlmostEqual(float(parsed.find("point").get("lat")), e["position"]["lat"])
        self.assertIn("SIMULATION", parsed.find("detail/remarks").text)


class SurfaceTests(unittest.TestCase):
    def test_empty_docs_without_model_or_worker(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(tools, "DOC_ROOT", Path(tmp)), patch.object(tools.subprocess, "run") as worker:
            self.assertEqual(tools.reference("list_reference_docs", {})["state"], "empty")
            self.assertEqual(tools.reference("search_reference_docs_semantic", {"query":"terminology"})["count"], 0)
            worker.assert_not_called()

    def test_reference_path_traversal_and_unknown_operations_rejected(self):
        for name, a in [("get_reference_section", {"doc_id":"../secret", "title_query":"x"}),
                        ("search_reference_docs", {"query":"x", "limit":True}),
                        ("shell_exec", {})]:
            with self.assertRaises(ValueError):
                tools.reference(name,a)

    def test_extension_preserves_existing_tools_and_denies_unconfirmed_write(self):
        module = types.SimpleNamespace(TOOLS=[{"name":"original"}], call=lambda name,args:{"original":name})
        tools.install(module)
        tools.install(module)
        self.assertEqual(module.call("original",{}), {"original":"original"})
        self.assertEqual(len([t for t in module.TOOLS if t["name"]=="simulation_read"]),1)
        result = json.loads(module.call("simulation_control",{"operation":"stop","arguments":{}})["content"][0]["text"])
        self.assertTrue(result["confirmation_required"])


class TransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_mtls_fanout_unix_control_and_persistence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            key, cert = root/"key.pem", root/"cert.pem"
            subprocess.run(["openssl","req","-x509","-newkey","rsa:2048","-nodes","-days","1",
                "-keyout",str(key),"-out",str(cert),"-subj","/CN=localhost",
                "-addext","subjectAltName=DNS:localhost"],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(cert,key)
            context.load_verify_locations(cafile=str(cert))
            context.verify_mode = ssl.CERT_REQUIRED
            writers, received, tasks = set(), [], set()

            async def peer(reader, writer):
                task = asyncio.current_task()
                tasks.add(task)
                writers.add(writer)
                try:
                    while data := await reader.read(16384):
                        received.append(data)
                        for other in list(writers):
                            other.write(data)
                            await other.drain()
                finally:
                    writers.discard(writer)
                    writer.close()
                    tasks.discard(task)

            server = await asyncio.start_server(peer,"127.0.0.1",0,ssl=context)
            port = server.sockets[0].getsockname()[1]
            config={"host":"127.0.0.1","port":port,"server_name":"localhost","ca_file":str(cert),
                "identities":[{"cert_file":str(cert),"key_file":str(key)} for _ in range(4)],
                "state_file":str(root/"state.json"),"tick_seconds":.05}
            d = Daemon(config)
            unix = True
            try:
                control = await asyncio.start_unix_server(d.client,str(root/"control.sock"),limit=65536)
            except PermissionError:
                # Some execution sandboxes prohibit AF_UNIX. Exercise the same
                # framed handler over loopback here; verify AF_UNIX on the node.
                unix = False
                control = await asyncio.start_server(d.client,"127.0.0.1",0,limit=65536)
            ticker = asyncio.create_task(d.tick())
            try:
                result = await d.command("create",args(position={"lat":55.71,"lon":13.21},count=4))
                self.assertTrue(result["ok"])
                for _ in range(100):
                    if len(d.observed)==4:
                        break
                    await asyncio.sleep(.02)
                self.assertEqual(len(d.observed),4)
                self.assertEqual(len(writers),4)
                self.assertTrue(all(s.info["connected"] for s in d.sessions.values()))
                self.assertIn(b"SIM-DEMO-HQ",b"".join(received))
                if unix:
                    with patch.object(tools,"SOCKET",str(root/"control.sock")):
                        status=await asyncio.to_thread(tools.simulation,"status",{})
                else:
                    r,w=await asyncio.open_connection("127.0.0.1",control.sockets[0].getsockname()[1])
                    w.write(b'{"operation":"status","arguments":{}}\n'); await w.drain()
                    status=json.loads(await r.readline())
                    w.close(); await w.wait_closed()
                self.assertEqual(status["identity_capacity"],4)
                self.assertEqual(len(status["observed_via_tak"]),4)
                restored=World(json.loads((root/"state.json").read_text()),capacity=4)
                self.assertEqual(len(restored.entities()),4)
            finally:
                ticker.cancel()
                for s in d.sessions.values(): s.task.cancel()
                await asyncio.gather(ticker,*(s.task for s in d.sessions.values()),return_exceptions=True)
                control.close(); await control.wait_closed()
                server.close(); await server.wait_closed()
                for t in list(tasks): t.cancel()
                await asyncio.gather(*tasks,return_exceptions=True)


if __name__ == "__main__":
    unittest.main()
