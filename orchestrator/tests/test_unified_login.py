import unittest
from types import SimpleNamespace
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from orchestrator_api import ui,martine
from orchestrator_api.auth import verify_token

class UnifiedLoginTests(unittest.TestCase):
    def setUp(self):
        app=FastAPI();app.include_router(ui.router);app.include_router(martine.router);self.client=TestClient(app,base_url='https://test.example')
        auth=SimpleNamespace(operator_user='operator',operator_password='fixture-password',session_secret='fixture-secret')
        self.config=patch.object(ui,'load_secrets_config',return_value=SimpleNamespace(auth=auth));self.config.start();self.addCleanup(self.config.stop)
        self.chatconfig=patch.object(martine,'load_secrets_config',return_value=SimpleNamespace(auth=auth));self.chatconfig.start();self.addCleanup(self.chatconfig.stop)
    def test_operator_uses_main_login_and_arbitrary_role_has_no_effect(self):
        response=self.client.post('/api/login',json={'username':'operator','password':'fixture-password','role':'anything'})
        self.assertEqual(response.status_code,200);self.assertNotIn('role',response.json())
        self.assertNotIn('taks_role',response.headers.get('set-cookie',''))
        self.assertTrue(verify_token(self.client.cookies['taks_auth'],'fixture-secret'))
    def test_normal_user_uses_same_login_and_main_shell_without_operator_authority(self):
        with patch.object(martine,'available_nodes',return_value=[{'node_id':'unit.example','fqdn':'unit.example','aws_state':'running'}]),patch.object(martine,'_call',return_value={'ok':True,'ticket':'signed-node-ticket','user':{'username':'alex','admin':False}}):
            response=self.client.post('/api/login',json={'username':'alex','password':'fixture','role':'admin'})
        self.assertEqual(response.status_code,200)
        self.assertFalse(verify_token(self.client.cookies['taks_martine'],'fixture-secret'))
        response=self.client.get('/');self.assertEqual(response.status_code,200)
        self.assertIn('data-operator="0"',response.text);
        self.assertEqual(self.client.post('/api/v2/units/unit/logo',files={'file':('logo.png',b'png','image/png')}).status_code,401);
        self.assertIn('data-route="/martine"',response.text)
        self.assertEqual(self.client.get('/martine',follow_redirects=False).headers['location'],'/#/martine')

    def test_fresh_pending_registry_node_is_available_but_stale_record_is_not(self):
        with patch.object(martine,'list_nodes',return_value=[{'node_id':'fresh','fqdn':'fresh.example','status':'online','aws_state':'pending','last_seen_ts':990},{'node_id':'old','fqdn':'old.example','status':'online','aws_state':'running','last_seen_ts':1}]),patch.object(martine.time,'time',return_value=1000):
            self.assertEqual([n['node_id'] for n in martine.available_nodes()],['fresh'])
