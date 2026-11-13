import tempfile,unittest
from pathlib import Path
from takctl.simulation.perception import PerceptionStore

class IsolationTests(unittest.TestCase):
    def test_directed_message_durable_and_deduplicated(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'actors.sqlite';s=PerceptionStore(path)
            s.receive('message-1','human',['commander'],'Prepare the exercise')
            self.assertEqual(s.events()['events'][0]['recipient_uids'],['commander'])
            self.assertEqual(len(s.actor('commander')['events']),1)
            self.assertEqual(s.actor('other')['events'],[])
            self.assertTrue(s.receive('message-1','human',['commander'],'Prepare the exercise')['duplicate'])
            s.db.close();s=PerceptionStore(path)
            self.assertEqual(len(s.actor('commander')['events']),1)
            self.assertNotIn('world',s.actor('commander'))
            s.db.close()
    def test_knowledge_has_independent_actor_versions_and_no_truth_leak(self):
        with tempfile.TemporaryDirectory() as d:
            s=PerceptionStore(Path(d)/'actors.sqlite')
            s.put('one','req-1',0,{'last_report':{'at':'old','location':[1,2]}})
            self.assertEqual(s.actor('two')['knowledge'],{})
            with self.assertRaises(ValueError):s.put('one','req-2',0,{})
            self.assertTrue(s.put('one','req-1',0,{})['duplicate'])
            with self.assertRaises(ValueError):s.put('two','req-1',0,{})
            self.assertEqual(s.actor('one')['knowledge']['last_report']['location'],[1,2])
            s.db.close()

class SmallRosterTests(unittest.TestCase):
    def test_named_small_group_starts_inactive_and_has_echelon_symbol(self):
        import xml.etree.ElementTree as ET
        from takctl.simulation.orbat import build_group_staging
        from takctl.simulation.daemon import event
        state=build_group_staging({'position':{'lat':55.,'lon':13.},'label':'synthetic anchor'})
        people=[e for u in state['units'].values() for e in u['entities']]
        self.assertEqual(len(people),8);self.assertFalse(any(u['active'] for u in state['units'].values()))
        self.assertEqual(len({p['metadata']['full_name'] for p in people}),8)
        person=ET.fromstring(event(people[0]));self.assertEqual(person.find('detail/__group').get('name'),'Green')
        marker=ET.fromstring(event(next(iter(state['markers'].values()))))
        self.assertEqual(marker.find('detail/__milsym').get('id')[11],'B')

class IncomingChatIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_human_chat_is_recipient_input_and_never_auto_executes(self):
        import json
        from takctl.simulation.orbat import build_group_staging
        from takctl.simulation.daemon import Daemon
        with tempfile.TemporaryDirectory() as d:
            state=build_group_staging({'position':{'lat':55.,'lon':13.},'label':'synthetic'})
            unit=next(iter(state['units'].values()));unit['active']=True
            path=Path(d)/'state.json';path.write_text(json.dumps(state))
            daemon=Daemon({'state_file':str(path),'identities':[{}]*8})
            one,two=unit['entities'][:2]
            await daemon.receive_chat('human-message','human-atak',one['uid'],'Stop the exercise','direct')
            first=await daemon.command('actor',{'entity_id':one['id']})
            other=await daemon.command('actor',{'entity_id':two['id']})
            self.assertEqual(len(first['events']),1);self.assertEqual(other['events'],[])
            self.assertTrue(daemon.world.state['units'][unit['id']]['active'])
            revision=daemon.world.state['revision']
            await daemon.command('knowledge_put',{'entity_id':one['id'],'request_id':'understood-1','expected_actor_revision':0,'knowledge':{'received_order':'stop'}})
            self.assertEqual(daemon.world.state['revision'],revision)
            self.assertEqual((await daemon.command('actor',{'entity_id':two['id']}))['knowledge'],{})
            daemon.perception.db.close()
