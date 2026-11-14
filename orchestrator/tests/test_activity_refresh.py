import asyncio
import ast
from pathlib import Path
from types import SimpleNamespace
from typing import Any,Dict,Optional
import unittest
from unittest.mock import Mock,patch
from orchestrator_core import activity_observer

class RefreshTests(unittest.IsolatedAsyncioTestCase):
 async def test_in_flight_sample_cannot_satisfy_a_new_pretermination_check(self):
  state={'instance':'i-fixture','wake':asyncio.Event(),'sampled':asyncio.Event(),'generation':0,'sampling':True}
  with patch.dict(activity_observer._OBSERVERS,{'node':state},clear=True):
   task=asyncio.create_task(activity_observer.refresh('node','i-fixture'))
   await state['wake'].wait()
   state['generation']=1;state['sampled'].set();await asyncio.sleep(.01)
   self.assertFalse(task.done())
   state['generation']=2;state['sampled'].set();self.assertTrue(await task)
 async def test_wrong_instance_cannot_refresh_other_observer(self):
  with patch.dict(activity_observer._OBSERVERS,{},clear=True):self.assertFalse(await activity_observer.refresh('node','different'))

class ShutdownGuardTests(unittest.TestCase):
 def function(self):
  source=ast.parse((Path(__file__).resolve().parents[1]/'orchestrator_api/api_v2.py').read_text())
  f=next(n for n in source.body if isinstance(n,ast.FunctionDef) and n.name=='nodes_terminate');f.decorator_list=[]
  class HTTPError(Exception):
   def __init__(self,status_code,detail):self.status_code=status_code;super().__init__(detail)
  terminate=Mock(return_value={'current_state':'shutting-down'})
  env={'Request':object,'Optional':Optional,'Dict':Dict,'Any':Any,'Body':lambda **_:None,'HTTPException':HTTPError,
    'require_operator':lambda _:None,'get_node':lambda _:{'node_id':'node','fqdn':'node.example.test'},
    '_resolve_instance_for_node_record':lambda *_:{'instance_id':'i-12345678'},'aws_terminate':terminate,'upsert_node':Mock(return_value={})}
  exec(compile(ast.Module(body=[f],type_ignores=[]),'guard','exec'),env)
  return env['nodes_terminate'],terminate,HTTPError
 def test_incomplete_evidence_blocks_termination(self):
  f,terminate,error=self.function()
  with patch.object(activity_observer,'fresh_assessment',return_value={'eligible_for_idle_shutdown':False}):
   with self.assertRaises(error):f('node',object(),{'expected_instance_id':'i-12345678','require_idle_evidence':True})
  terminate.assert_not_called()
 def test_only_complete_fresh_proof_reaches_mock_termination(self):
  f,terminate,_=self.function()
  with patch.object(activity_observer,'fresh_assessment',return_value={'eligible_for_idle_shutdown':True}):
   self.assertTrue(f('node',object(),{'expected_instance_id':'i-12345678','require_idle_evidence':True})['ok'])
  terminate.assert_called_once_with('i-12345678',fqdn='node.example.test')
 def test_bad_flag_or_changed_identity_is_rejected(self):
  for body in ({'require_idle_evidence':'true'},{'expected_instance_id':'i-wrong','require_idle_evidence':True}):
   f,terminate,error=self.function()
   with self.assertRaises(error):f('node',object(),body)
   terminate.assert_not_called()

class NativeEnvelopeTests(unittest.TestCase):
 def test_both_v1_wire_formats_preserve_completeness(self):
  import json
  evidence={'version':1,'complete':True,'epoch':'fixture','last_human_event':None}
  for payload in (evidence,{'content':[{'type':'text','text':json.dumps(evidence)}]}):
   self.assertEqual(activity_observer.decode_external_result({'result':payload}),evidence)
 def test_arbitrary_success_is_not_evidence(self):
  with self.assertRaises(ValueError):activity_observer.decode_external_result({'result':{'ok':True}})
