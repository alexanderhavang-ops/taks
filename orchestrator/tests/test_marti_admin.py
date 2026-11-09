import base64
import io
import json
import unittest
import urllib.error
from unittest.mock import patch
from orchestrator_core import marti_admin as m


class Response(io.BytesIO):
    status = 200


class MartiAdminTests(unittest.TestCase):
    def setUp(self):
        self.node = patch.object(m, 'get_node', return_value={
            'fqdn': 'taklabs.example.com', 'unit_path': 'taklabs'}).start()
        self.bootstrap = patch.object(m, 'effective_bootstrap_for_bundle', return_value={
            'conf_d': {'admin.conf': {'takctl_admin_user': 'takadmin'}},
            'secrets_d': {'admin.conf': {'takctl_admin_password': 'PRIVATE'}}}).start()
        self.opener = patch.object(m.urllib.request, 'build_opener').start().return_value
        self.addCleanup(patch.stopall)

    def test_installer_admin_used_for_fixed_read_only_endpoints(self):
        def respond(request, **kwargs):
            self.assertEqual(request.method, 'GET')
            self.assertTrue(request.full_url.startswith('https://taklabs.example.com:8446/Marti/api/'))
            self.assertEqual(request.get_header('Authorization'), 'Basic ' +
                             base64.b64encode(b'takadmin:PRIVATE').decode())
            return Response(json.dumps({'callsign': 'Alexander', 'password': 'PRIVATE'}).encode())
        self.opener.open.side_effect = respond
        result = m.diagnose('taklabs.example.com')
        self.assertTrue(result['ok'])
        self.assertEqual(self.opener.open.call_count, 3)
        self.assertNotIn('PRIVATE', json.dumps(result))
        self.assertEqual(result['checks']['subscriptions']['data']['callsign'], 'Alexander')

    def test_missing_admin_secret_does_not_try_network(self):
        self.bootstrap.return_value = {'conf_d': {}, 'secrets_d': {}}
        self.assertFalse(m.diagnose('taklabs.example.com')['ok'])
        self.opener.open.assert_not_called()

    def test_error_body_and_redirect_are_not_exposed(self):
        self.opener.open.side_effect = urllib.error.HTTPError('https://example.com', 403,
            'PRIVATE', {}, io.BytesIO(b'PRIVATE'))
        result = m.diagnose('taklabs.example.com')
        self.assertFalse(result['ok'])
        self.assertEqual(result['checks']['subscriptions']['http_status'], 403)
        self.assertNotIn('PRIVATE', json.dumps(result))
        self.assertIsNone(m.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://elsewhere'))

    def test_invalid_or_unknown_node_rejected(self):
        self.assertFalse(m.diagnose('../elsewhere')['ok'])
        self.node.assert_not_called()
        self.node.return_value = None
        self.assertFalse(m.diagnose('unknown')['ok'])
        self.bootstrap.assert_not_called()


if __name__ == '__main__':
    unittest.main()
