import asyncio
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

from takctl.simulation.model import World
from takctl.simulation.orbat import build_hv_staging
from takctl.simulation.daemon import Daemon, CotFrames, event
from takctl.onboarding.fal import parse_callsign


def fixture():
    anchors={k:{"position":{"lat":55.71,"lon":13.21},"label":"synthetic anchor"} for k in ("VQ","RQ","SQ","TQ")}
    return build_hv_staging(anchors)


class RosterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.state=fixture()

    def test_exact_headcount_and_unique_callsigns_slots_and_uids(self):
        state=self.state; people=[e for u in state["units"].values() for e in u["entities"]]
        self.assertEqual(len(people),520)
        for field in ("callsign","uid","identity_slot"):self.assertEqual(len({e[field] for e in people}),520)
        self.assertEqual({e["identity_slot"] for e in people},set(range(520)))
        self.assertEqual(len(state["units"]),70)
        self.assertEqual(len(state["markers"]),85)
        self.assertFalse(any(u["active"] for u in state["units"].values()))
        self.assertLess(len(json.dumps(state,separators=(",",":")).encode()),1048576)

    def test_authoritative_identity_grammar_and_local_alias_ambiguity(self):
        rows=self.state["orbat"]["actors"]
        actor=next(e for e in rows if e["callsign"]=="SIM-EATQ3")
        self.assertEqual(actor["local_callsign"],"EA3")
        parsed=parse_callsign(None,"EATQ3")
        self.assertEqual(parsed["individual"],3)
        self.assertEqual(len(self.state["orbat"]["local_aliases"]["EA3"]),3)
        self.assertIn("SIM-RQVQ1",{e["callsign"] for e in rows})
        self.assertEqual(self.state["orbat"]["staff_strengths"],{"S1":2,"S2":2,"S3/5":3,"S4":2,"S6":3})

    def test_hierarchy_has_existing_parents_and_marker_owners(self):
        nodes=self.state["orbat"]["nodes"]; ids={n["id"] for n in nodes}
        self.assertTrue(all(n["parent_id"] is None or n["parent_id"] in ids for n in nodes))
        self.assertTrue(all(n["owner_unit_id"] in self.state["units"] for n in nodes))
        self.assertEqual(sum(n["level"]=="group" for n in nodes),60)
        self.assertEqual(sum(n["level"]=="company" for n in nodes),3)
        for marker in self.state["markers"].values():
            xml=ET.fromstring(event(marker))
            self.assertIsNone(xml.find("detail/contact").get("endpoint"))
            if marker["role"]=="HQ":self.assertEqual(xml.find("detail/__group").get("role"),"HQ")

    def test_activation_ramps_without_reusing_a_live_certificate(self):
        w=World(self.state,capacity=520)
        names=list(w.state["units"])
        for start in range(0,len(names),16):
            commands=[{"operation":"activate","arguments":{"unit_id":uid}} for uid in names[start:start+16]]
            w.apply("batch",{"request_id":"ramp-"+str(start),"expected_revision":w.state["revision"],"commands":commands})
        self.assertEqual(len(w.entities()),520)
        self.assertEqual(len({e["identity_slot"] for e in w.entities()}),520)
        other=World(capacity=2)
        other.apply("create",{"unit_id":"one","position":{"lat":55.71,"lon":13.21},"count":2,"request_id":"one","expected_revision":0})
        other.apply("deactivate",{"unit_id":"one","request_id":"off","expected_revision":1})
        other.apply("create",{"unit_id":"two","position":{"lat":55.71,"lon":13.21},"count":2,"request_id":"two","expected_revision":2})
        with self.assertRaisesRegex(ValueError,"slots"):
            other.apply("activate",{"unit_id":"one","request_id":"bad","expected_revision":3})


class ReceiveTests(unittest.TestCase):
    def test_shared_dedup_drains_every_stream_but_parses_only_unique_frames(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Daemon({"state_file":str(Path(tmp)/"state.json"),"identities":[]})
            parsers=[CotFrames(d.accept_frame) for _ in range(520)]
            raw=b'<event uid="same" type="a-f-G"><point lat="55" lon="13"/></event>'
            accepted=[]
            for parser in parsers:
                accepted.extend(parser.feed(raw[:21]));accepted.extend(parser.feed(raw[21:]))
            self.assertEqual(len(accepted),1)
            self.assertEqual(sum(p.frames_seen for p in parsers),520)
            self.assertEqual(d.frame_counts,{"unique":1,"duplicates":519})
            self.assertEqual(len(parsers[0].feed(raw.replace(b"same",b"new"))),1)


class PaginationTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_people_can_be_read_in_bounded_pages_before_activation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"state.json";path.write_text(json.dumps(fixture()))
            d=Daemon({"state_file":str(path),"identities":[{}]*520})
            seen=set()
            for start in range(0,520,64):
                result=await d.command("status",{"entity_offset":start,"entity_limit":64})
                page=[e for u in result["units"] for e in u["entities"]]
                self.assertLessEqual(len(page),64)
                seen.update(e["uid"] for e in page)
                self.assertEqual(result["summary"]["stored_entities"],520)
                self.assertLess(len(json.dumps(result).encode()),1048576)
            self.assertEqual(len(seen),520)
            self.assertEqual((await d.command("orbat",{}))["orbat"]["personnel"],520)


if __name__=="__main__":unittest.main()
