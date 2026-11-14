import tempfile,unittest
from pathlib import Path
from orchestrator_core.activity import ActivityStore,monitoring

class ActivityTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.s=ActivityStore(Path(self.tmp.name)/'a.sqlite');self.addCleanup(self.s.close)
 def verified_quiet(self,watermark=0):
  self.s.connection('node','i-one',True,now=100)
  for now in range(100,14561,60):
   self.s.verified('node','i-one',True,now=now)
   self.s.component('bridge','b',now);self.s.component('devops','d',now);self.s.external('node','i-one',{'complete':True,'epoch':'n','last_human_event':watermark},now)
 def test_real_quiet_can_qualify_but_stale_data_cannot(self):
  self.verified_quiet();self.assertTrue(self.s.assess('node','i-one',14560)['eligible_for_idle_shutdown'])
  self.assertFalse(self.s.assess('node','i-one',14700)['eligible_for_idle_shutdown'])
 def test_bot_periodic_does_not_extend_idle_but_unknown_chat_does(self):
  self.verified_quiet();self.s.observed('node','i-one','bot',now=14550)
  self.assertTrue(self.s.assess('node','i-one',14560)['eligible_for_idle_shutdown'])
  self.s.observed('node','i-one','ambiguous','bot chat',now=14551)
  self.assertFalse(self.s.assess('node','i-one',14560)['eligible_for_idle_shutdown'])
 def test_monitoring_does_not_reset_tool_clock(self):
  self.verified_quiet();self.assertFalse(self.s.note_tool('node','i-one','taks','diagnostic_log',{},14550))
  self.assertTrue(self.s.assess('node','i-one',14560)['eligible_for_idle_shutdown'])
  self.s.note_tool('node','i-one','taks','simulation_control',{'operation':'move','password':'never-stored'},14550)
  self.assertFalse(self.s.assess('node','i-one',14560)['eligible_for_idle_shutdown'])
  self.assertNotIn('never-stored',str(self.s.db.execute('SELECT * FROM audit').fetchall()))
 def test_gap_reconnect_and_replacement_reset_coverage(self):
  self.verified_quiet();self.s.verified('node','i-one',False,'filtered feed',14550)
  self.assertFalse(self.s.assess('node','i-one',14560)['eligible_for_idle_shutdown'])
  self.s.verified('node','i-one',True,now=14560)
  self.assertFalse(self.s.assess('node','i-one',14561)['eligible_for_idle_shutdown'])
  self.assertFalse(self.s.assess('node','i-two',14561)['eligible_for_idle_shutdown'])
 def test_unseen_node_never_proves_history(self):
  self.assertFalse(self.s.assess('node','i-one',999999)['eligible_for_idle_shutdown'])
 def test_actor_reads_count_but_status_polling_does_not(self):
  self.assertTrue(monitoring('taks','simulation_read',{'view':'status'}))
  self.assertFalse(monitoring('taks','simulation_read',{'view':'actor'}))

class DirectWatermarkTests(unittest.TestCase):
 setUp=ActivityTests.setUp
 verified_quiet=ActivityTests.verified_quiet
 def test_initial_snapshot_is_baseline_and_only_new_inputs_extend_clock(self):
  self.verified_quiet(watermark=10)
  evidence={'complete':True,'epoch':'n','last_human_event':10}
  self.s.external('node','i-one',evidence,now=14560)
  self.assertTrue(self.s.assess('node','i-one',14560)['eligible_for_idle_shutdown'])
  self.s.external('node','i-one',{**evidence,'last_human_event':11},now=14561)
  result=self.s.assess('node','i-one',14561)
  self.assertFalse(result['eligible_for_idle_shutdown']);self.assertEqual(result['last_direct_input_at'],14561)
 def test_watermark_regression_restarts_coverage(self):
  self.verified_quiet(watermark=10)
  self.s.external('node','i-one',{'complete':True,'epoch':'n','last_human_event':0},14560)
  result=self.s.assess('node','i-one',14560)
  self.assertEqual(result['coverage_since'],14560)
  self.assertFalse(result['eligible_for_idle_shutdown'])
 def test_invalid_watermark_never_establishes_coverage(self):
  with self.assertRaises(ValueError):self.s.external('node','i-one',{'complete':True,'epoch':'n','last_human_event':float('inf')},now=100)

 def test_first_snapshot_cannot_reuse_legacy_channel_history(self):
  self.verified_quiet()
  self.s.db.execute("UPDATE nodes SET external_epoch=NULL,last_external=NULL");self.s.db.commit()
  self.s.external('node','i-one',{'complete':True,'epoch':'n','last_human_event':10},14560)
  result=self.s.assess('node','i-one',14560)
  self.assertEqual(result['coverage_since'],14560)
  self.assertFalse(result['eligible_for_idle_shutdown'])
  self.assertIsNone(result['last_direct_input_at'])

class KnownIdleTakdiagTests(unittest.TestCase):
 setUp=ActivityTests.setUp
 verified_quiet=ActivityTests.verified_quiet
 def test_takdiag_monitoring_builds_and_periodic_presence_are_idle(self):
  self.verified_quiet()
  for tool in ('diagnostic_log','service_read','taks_bundle_prepare_start'):
   self.assertFalse(self.s.note_tool('node','i-one','devops',tool,{},14550))
  self.s.observed('node','i-one','bot',now=14550)
  result=self.s.assess('node','i-one',14560)
  self.assertEqual(result['observed_state'],'idle')
  self.assertTrue(result['eligible_for_idle_shutdown'])
  self.assertIsNone(result['last_non_monitoring_tool_at'])
