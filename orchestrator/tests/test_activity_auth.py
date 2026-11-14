from types import SimpleNamespace
import unittest
from unittest.mock import patch
from orchestrator_api import service_auth

class ActivityAuth(unittest.TestCase):
 def request(self,method,path,host='127.0.0.1'):
  return SimpleNamespace(method=method,url=SimpleNamespace(path=path),client=SimpleNamespace(host=host),headers={'authorization':'Bearer fixture-business'})
 def test_business_has_product_log_and_activity_read_without_devops_audit_write(self):
  with patch.object(service_auth,'business_service_token',return_value='fixture-business'):
   self.assertTrue(service_auth.service_auth_ok(self.request('POST','/api/v2/nodes/node/product-journal')))
   self.assertTrue(service_auth.service_auth_ok(self.request('GET','/api/v2/nodes/node/activity')))
   self.assertFalse(service_auth.service_auth_ok(self.request('POST','/api/v2/activity/audit')))
   self.assertFalse(service_auth.service_auth_ok(self.request('POST','/api/v2/nodes/node/mcp/devops')))
 def test_remote_or_bad_node_path_cannot_use_loopback_credentials(self):
  with patch.object(service_auth,'business_service_token',return_value='fixture-business'):
   self.assertFalse(service_auth.service_auth_ok(self.request('GET','/api/v2/nodes/node/activity','203.0.113.1')))
   self.assertFalse(service_auth.service_auth_ok(self.request('GET','/api/v2/nodes/../activity')))
