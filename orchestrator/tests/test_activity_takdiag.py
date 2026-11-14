"""Acceptance baseline: takdiag's known idle feed contains only Martine reports."""
import tempfile
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET
from orchestrator_core.activity import ActivityStore
from orchestrator_core.activity_observer import classify,Frames

class TakdiagIdleAcceptance(unittest.TestCase):
 def test_martine_only_takdiag_is_idle_and_can_complete_verified_window(self):
  with tempfile.TemporaryDirectory() as folder:
   s=ActivityStore(Path(folder)/'evidence.sqlite')
   try:
    node='takdiag.example.test';instance='fixture-instance'
    s.connection(node,instance,True,now=100)
    packet=b'<event uid="ANDROID-MARTINE" type="a-f-G-U-C"><detail><contact callsign="Martine"/></detail></event>'
    for now in range(100,14561,30):
     event=Frames().feed(packet)[0]
     self.assertEqual(classify(event,{'ANDROID-MARTINE'}),'bot')
     s.observed(node,instance,'bot',now=now)
     s.verified(node,instance,True,now=now)
     for component in ('bridge','devops'):s.component(component,'fixture-epoch',now=now)
     s.external(node,instance,{'complete':True,'epoch':'fixture-epoch','last_human_event':0},now)
     s.note_tool(node,instance,'taks','service_read',{'service':'activity','operation':'status'},now=now)
    result=s.assess(node,instance,14560)
    self.assertEqual(result['observed_state'],'idle')
    self.assertTrue(result['eligible_for_idle_shutdown'])
    self.assertIsNone(result['last_non_bot_cot_at'])
    self.assertIsNone(result['last_non_monitoring_tool_at'])
    self.assertGreater(result['ignored_periodic_bot_frames'],400)
   finally:s.close()
 def test_real_client_cannot_hide_behind_martine_callsign(self):
  event=ET.fromstring('<event uid="REAL-CLIENT" type="a-f-G-U-C"><detail><contact callsign="Martine"/></detail></event>')
  self.assertEqual(classify(event,{'ANDROID-MARTINE'}),'activity')
 def test_bot_chat_needs_attribution_and_is_not_silently_ignored(self):
  event=ET.fromstring('<event uid="chat-one" type="b-t-f"><detail><link uid="ANDROID-MARTINE" relation="p-p"/></detail></event>')
  self.assertEqual(classify(event,{'ANDROID-MARTINE'}),'ambiguous')

 def test_server_protocol_handshake_is_not_user_activity(self):
  event=ET.fromstring('<event uid="server-session" type="t-x-takp-v"/>')
  self.assertEqual(classify(event,{'ANDROID-MARTINE'}),'control')
