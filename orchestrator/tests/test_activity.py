import tempfile,unittest
from pathlib import Path
from orchestrator_core.activity import ActivityStore,monitoring

class ActivityTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.s=ActivityStore(Path(self.tmp.name)/'a.sqlite');self.addCleanup(self.s.close)
 def verified_quiet(self):
  self.s.connection('node','i-one',True,now=100)
  for now in range(100,14561,60):
   self.s.verified('node','i-one',True,now=now)
   self.s.component('bridge','b',now);self.s.component('devops','d',now);self.s.component('node_external:node','n',now)
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
