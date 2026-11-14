import json
import unittest
from unittest.mock import Mock
from taks_mcp.journal import takctl_journal

class JournalTest(unittest.TestCase):
 def api(self,**payload):return Mock(return_value={'result':{'content':[{'type':'text','text':json.dumps(payload)}]}})
 def test_fixed_unit_bounded_and_redacted(self):
  api=self.api(exit_code=0,stdout='hello\npassword=fixture\n',stderr='')
  r=takctl_journal(api,'takdiag.example.test',100)
  self.assertTrue(r['ok']);self.assertNotIn('fixture',r['content']);self.assertFalse(r['inactivity_proof'])
  self.assertEqual(api.call_args.args[2],{'source':'takctl','lines':100})
  self.assertTrue(api.call_args.args[1].endswith('/product-journal'))
 def test_failure_and_empty_do_not_prove_inactivity(self):
  r=takctl_journal(self.api(exit_code=1,stdout='',stderr='Permission denied'),'node')
  self.assertFalse(r['ok']);self.assertEqual(r['detail'],'Permission denied')
  r=takctl_journal(self.api(exit_code=0,stdout='-- No entries --',stderr=''),'node')
  self.assertFalse(r['ok']);self.assertFalse(r['inactivity_proof'])
 def test_invalid_scope_never_calls_api(self):
  api=Mock()
  for node,lines in (('../node',4),('node',101),('node',True)):
   self.assertFalse(takctl_journal(api,node,lines)['ok'])
  api.assert_not_called()
