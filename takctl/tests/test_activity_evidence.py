import json
from pathlib import Path
import tempfile
import unittest
from takctl.services.activity_evidence import pulse,note,snapshot

class DirectActivityTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.root=Path(self.tmp.name)/'db';self.agent=Path(self.tmp.name)/'agent.py';self.agent.write_text('IDLE_AUDIT_HOOK_VERSION = 1\n')
 def read(self,now):return snapshot(root=self.root,agent=self.agent,now=now)
 def test_known_idle_bot_services_have_complete_input_coverage(self):
  for name in ('xmpp','voice'):pulse(name,True,root=self.root,now=100,epoch=name+'-process')
  result=self.read(110);self.assertTrue(result['complete']);self.assertIsNone(result['last_human_event'])
  self.assertFalse(result['retains_message_bodies'])
 def test_human_use_all_channels_records_only_watermark(self):
  for channel in ('agent','xmpp','voice'):note(channel,root=self.root,now=200)
  for name in ('xmpp','voice'):pulse(name,True,root=self.root,now=200,epoch='test')
  result=self.read(201);self.assertEqual(result['last_human_event'],202)
  self.assertNotIn('body',json.dumps(result))
 def test_brief_disconnect_changes_coverage_epoch(self):
  for name in ('xmpp','voice'):pulse(name,True,root=self.root,now=100,epoch='test')
  before=self.read(110)['epoch'];pulse('xmpp',False,root=self.root,now=111,epoch='test')
  self.assertFalse(self.read(112)['complete'])
  pulse('xmpp',True,root=self.root,now=113,epoch='test')
  self.assertNotEqual(before,self.read(114)['epoch'])
 def test_stale_or_unpatched_worker_is_not_complete(self):
  for name in ('xmpp','voice'):pulse(name,True,root=self.root,now=100,epoch='test')
  self.assertFalse(self.read(200)['complete'])
  self.agent.write_text('# old worker\n');self.assertFalse(self.read(101)['complete'])
