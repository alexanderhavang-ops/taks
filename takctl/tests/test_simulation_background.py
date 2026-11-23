import copy
import json
import unittest
from takctl.simulation.model import World, offset, distance


class BackgroundTest(unittest.TestCase):
    def setUp(self):
        self.w=World();self.w.apply('create',{'unit_id':'test','position':{'lat':1,'lon':1},'count':1,'callsign':'SIM-T','request_id':'create','expected_revision':0})
        self.e=self.w.entities()[0];self.start=dict(self.e['position']);self.end=offset(self.start,20,0)
    def command(self,op,**args):
        result=self.w.apply(op,{**({} if op in ('pause','resume') else {'unit_id':'test'}),'request_id':'r'+str(self.w.state['revision']),'expected_revision':self.w.state['revision'],**args})
        self.e=self.w.state['units']['test']['entities'][0]
        return result
    def put(self,repeat=True):
        self.command('background_put',entity_id=self.e['id'],waypoints=[{'position':self.end,'travel_s':20,'wait_s':10},{'position':self.start,'travel_s':20,'wait_s':10}],repeat=repeat,delay_s=5)
    def test_walk_wait_repeat_restart_and_pause(self):
        self.put();self.w.advance(15)
        self.assertAlmostEqual(distance(self.start,self.e['position']),10,places=3)
        self.w=World(json.loads(json.dumps(self.w.state)));self.e=self.w.entities()[0]
        self.w.advance(15);self.assertLess(distance(self.end,self.e['position']),.01)
        self.command('pause');p=copy.deepcopy(self.e['position']);self.w.advance(100);self.assertEqual(p,self.e['position'])
        self.command('resume');self.w.advance(35);self.assertLess(distance(self.start,self.e['position']),.01)
        self.assertEqual(self.e['background']['cycles'],1)
    def test_explicit_order_suspends_without_snap_back(self):
        self.put();self.w.advance(15)
        self.command('entity_move',entity_id=self.e['id'],path=[offset(self.end,30,0)],duration_s=40)
        self.assertFalse(self.e['background']['enabled']);self.w.advance(40)
        p=copy.deepcopy(self.e['position']);self.w.advance(100);self.assertEqual(p,self.e['position'])
        with self.assertRaisesRegex(ValueError,'replace background'):self.command('background_resume',entity_id=self.e['id'])
    def test_injury_and_inactive_stop_ambient(self):
        self.put();self.command('entity_patch',entity_id=self.e['id'],health_state='wounded')
        p=copy.deepcopy(self.e['position']);self.w.advance(40);self.assertEqual(p,self.e['position'])
        self.assertFalse(self.e['background']['enabled'])
        self.command('deactivate');self.put();elapsed=self.e['background']['elapsed_s'];self.w.advance(100)
        self.assertEqual(elapsed,self.e['background']['elapsed_s'])
    def test_one_shot_and_validation_are_atomic(self):
        self.put(False);self.w.advance(100);self.assertEqual(self.e['background']['phase'],'completed')
        prior=copy.deepcopy(self.w.state)
        with self.assertRaises(ValueError):self.command('background_put',entity_id=self.e['id'],waypoints=[{'position':self.end,'travel_s':20,'wait_s':10}],repeat=True)
        self.assertEqual(prior,self.w.state)

    def test_formation_with_512_waypoints_keeps_offsets_after_many_loops(self):
        w = World()
        w.apply("create", {"unit_id": "group", "request_id": "new", "expected_revision": 0,
                           "count": 3, "position": self.start})
        waypoints = [{"position": self.end if i % 2 == 0 else self.start,
                      "travel_s": 10, "wait_s": 5} for i in range(512)]
        arguments = {"unit_id": "group", "request_id": "route", "expected_revision": 1,
                     "waypoints": waypoints, "repeat": True}
        self.assertLess(len(json.dumps({"operation": "background_put", "arguments": arguments})), 65536)
        result = w.apply("background_put", arguments)
        self.assertEqual(result["background"]["waypoint_count"], 512)
        cycle = 512 * 15
        w.advance(10000 * cycle + cycle - 10)
        w = World(json.loads(json.dumps(w.state)))
        w.advance(15)
        unit = w.state["units"]["group"]
        self.assertEqual(unit["background"]["cycles"], 10001)
        self.assertEqual(unit["background"]["waypoint_index"], 0)
        self.assertAlmostEqual(distance(unit["position"], self.start), 10, places=3)
        for member in unit["entities"]:
            position = offset(unit["position"], member["north_m"], member["east_m"])
            self.assertEqual(member["position"], position)
        w.apply("stop", {"unit_id": "group", "request_id": "stop", "expected_revision": 2})
        stopped = copy.deepcopy(w.entities())
        w.advance(cycle)
        self.assertEqual(w.entities(), stopped)

    def test_legacy_route_keeps_saved_progress(self):
        self.put()
        bg = self.e["background"]
        from takctl.simulation.model import make_path
        bg["legs"] = [
            {"move": make_path(self.start, {"path": [self.end], "duration_s": 20}), "wait_s": 10},
            {"move": make_path(self.end, {"path": [self.start], "duration_s": 20}), "wait_s": 10},
        ]
        del bg["route"], bg["origin"]
        bg["elapsed_s"] = 15
        self.w = World(json.loads(json.dumps(self.w.state)))
        self.w.advance(5)
        self.assertAlmostEqual(distance(self.start, self.w.entities()[0]["position"]), 15, places=3)
