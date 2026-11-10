import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from orchestrator_api import martine

class MartineRelayTests(unittest.TestCase):
    def setUp(self):
        app=FastAPI();app.include_router(martine.router);self.client=TestClient(app)

    def test_user_session_cannot_switch_node_or_supply_admin_identity(self):
        session={'node_id':'own-node','ticket':'signed-ticket','user':{'username':'alice','admin':False}}
        with patch.object(martine,'_operator',return_value=False),patch.object(martine,'_decode',return_value=session),patch.object(martine,'_call',return_value={'ok':True}) as call:
            headers={'X-TAKS-Chat':'1'}
            self.assertEqual(self.client.post('/api/v2/martine/ask',headers=headers,json={'node_id':'other-node','message':'help'}).status_code,403)
            call.assert_not_called()
            self.assertEqual(self.client.post('/api/v2/martine/ask',headers=headers,json={'node_id':'own-node','message':'help','operator_user':'admin','principal':{'admin':True}}).status_code,200)
            self.assertEqual(call.call_args.args,('own-node','chat_submit',{'ticket':'signed-ticket','message':'help','conversation_id':'main'}))

    def test_login_uses_node_authentication_and_protected_cookie(self):
        auth=SimpleNamespace(session_secret='fixture-secret')
        with patch.object(martine,'_call',return_value={'ok':True,'ticket':'node-ticket','user':{'username':'alice','admin':False}}),patch.object(martine,'load_secrets_config',return_value=SimpleNamespace(auth=auth)):
            r=self.client.post('/api/v2/martine/login',headers={'X-TAKS-Chat':'1'},json={'node_id':'own-node','username':'alice','password':'fixture'})
            self.assertEqual(r.status_code,200)
            cookie=r.headers['set-cookie'];self.assertIn('HttpOnly',cookie);self.assertIn('Secure',cookie);self.assertIn('SameSite=lax',cookie)
            self.assertNotIn('fixture',r.text)

    def test_public_page_and_widget_do_not_require_devops(self):
        self.assertEqual(self.client.get('/martine').status_code,200)
        self.assertEqual(self.client.get('/martine-widget.js').status_code,200)
        with patch.object(martine,'_operator',return_value=False),patch.object(martine,'_decode',return_value=None):
            self.assertEqual(self.client.post('/api/v2/martine/ask',headers={'X-TAKS-Chat':'1'},json={'message':'help'}).status_code,401)
