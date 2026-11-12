from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from orchestrator_api import service_auth as auth


class BackupAuthTests(unittest.TestCase):
    def request(self, method, path, token, host='127.0.0.1'):
        return SimpleNamespace(method=method, url=SimpleNamespace(path=path),
                               client=SimpleNamespace(host=host),
                               headers={'authorization': 'Bearer ' + token})

    def test_backup_routes_allow_only_existing_devops_identity_on_loopback(self):
        routes = [('GET', '/api/v2/units/org/taklabs/backups'),
                  ('GET', '/api/v2/units/taklabs/backups/restore-selection'),
                  ('POST', '/api/v2/nodes/taklabs.example.com/backup'),
                  ('POST', '/api/v2/units/taklabs/backups/fresh-backup/verify'),
                  ('POST', '/api/v2/units/taklabs/backups/fresh-backup/select-restore')]
        with tempfile.TemporaryDirectory() as tmp:
            token_file = Path(tmp) / 'token'
            token_file.write_text('test-devops-token')
            with patch.object(auth, 'TOKEN_FILE', token_file), patch.object(auth, 'business_service_token', return_value='test-business-token'):
                for method, path in routes:
                    with self.subTest(path=path):
                        self.assertTrue(auth.service_auth_ok(self.request(method, path, 'test-devops-token')))
                        self.assertFalse(auth.service_auth_ok(self.request(method, path, 'test-business-token')))
                        self.assertFalse(auth.service_auth_ok(self.request(method, path, 'wrong-token')))
                        self.assertFalse(auth.service_auth_ok(self.request(method, path, 'test-devops-token', '203.0.113.1')))
                for method, path in [('GET', '/api/v2/units/taklabs/backups/fresh-backup/artifact'),
                                     ('DELETE', '/api/v2/units/taklabs/backups/fresh-backup'),
                                     ('POST', '/api/v2/units/../taklabs/backups/fresh-backup/verify'),
                                     ('POST', '/api/v2/nodes/../backup')]:
                    self.assertFalse(auth.service_auth_ok(self.request(method, path, 'test-devops-token')))
