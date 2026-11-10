import unittest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from takctl.web.core.business_authorization import install_business_authorization

class BusinessAuthorizationTests(unittest.TestCase):
    def setUp(self):
        app=FastAPI()
        for path in ('/api/users','/api/logs/read','/api/whoami','/api/martine/history','/api/onboarding/cards/opaque-token'):
            app.add_api_route(path,lambda:{'ok':True},methods=['GET'])
        install_business_authorization(app)
        self.client=TestClient(app)

    def test_normal_account_cannot_enter_admin_api_or_claim_role(self):
        with patch('takctl.services.business_access.request_actor',return_value={'admin':False}):
            for path in ('/api/users','/api/logs/read'):
                self.assertEqual(self.client.get(path,headers={'X-Admin':'true','X-Role':'admin'}).status_code,403)

    def test_admin_is_authorized_and_anonymous_is_rejected(self):
        with patch('takctl.services.business_access.request_actor',return_value={'admin':True}):
            self.assertEqual(self.client.get('/api/users').status_code,200)
        with patch('takctl.services.business_access.request_actor',side_effect=PermissionError):
            self.assertEqual(self.client.get('/api/users').status_code,401)
            self.assertEqual(self.client.get('/api/whoami').status_code,200)
            self.assertEqual(self.client.get('/api/onboarding/cards/opaque-token').status_code,200)
            self.assertEqual(self.client.get('/api/martine/history').status_code,200) # guarded by its own router

    def test_loopback_without_exact_internal_bearer_has_no_bypass(self):
        app=FastAPI();app.add_api_route('/api/users',lambda:{'ok':True});install_business_authorization(app)
        client=TestClient(app,client=('127.0.0.1',1234))
        with patch('takctl.web.api.orchestrator._read_local_orchestrator_secret',return_value='internal-test'),patch('takctl.services.business_access.request_actor',side_effect=PermissionError):
            self.assertEqual(client.get('/api/users').status_code,401)
            self.assertEqual(client.get('/api/users',headers={'Authorization':'Bearer wrong'}).status_code,401)
            self.assertEqual(client.get('/api/users',headers={'Authorization':'Bearer internal-test'}).status_code,200)
