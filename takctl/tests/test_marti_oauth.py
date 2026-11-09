import unittest
from unittest.mock import Mock, patch
from takctl.services import marti_api as m


class MartiOAuthTests(unittest.TestCase):
    def setUp(self):
        m._TOKEN_CACHE = m._TokenCache()
        self.config = patch.object(m, 'load_config', return_value={
            'fqdn': 'node.example.com', 'takctl_admin_user': 'admin',
            'marti_api_base': 'https://127.0.0.1:8446'}).start()
        self.secrets = patch.object(m, 'load_secrets', return_value={
            'takctl_admin_password': 'PRIVATE', 'marti_api_password': 'OBSOLETE'}).start()
        self.post = patch.object(m.requests, 'post').start()
        self.post.return_value = Mock(status_code=200)
        self.post.return_value.json.return_value = {'access_token': 'TOKEN',
            'token_type': 'Bearer', 'expires_in': 3600}
        self.request = patch.object(m.requests, 'request').start()
        self.request.return_value = Mock(status_code=200)
        self.addCleanup(patch.stopall)

    def test_canonical_credential_form_login_verified_tls_and_cache(self):
        self.assertEqual(m.get_auth_header(), {'Authorization': 'Bearer TOKEN'})
        self.assertEqual(m.get_access_token(), 'TOKEN')
        self.post.assert_called_once_with('https://node.example.com:8446/oauth/token',
            data={'grant_type': 'password', 'username': 'admin', 'password': 'PRIVATE'},
            timeout=20, verify=True, allow_redirects=False)

    def test_unauthorized_refreshes_once_but_forbidden_does_not(self):
        self.request.side_effect = [Mock(status_code=401), Mock(status_code=200)]
        self.assertEqual(m.marti_get('/Marti/api/subscriptions/all').status_code, 200)
        self.assertEqual(self.post.call_count, 2)
        self.request.side_effect = [Mock(status_code=403)]
        self.assertEqual(m.marti_get('/Marti/api/subscriptions/all').status_code, 403)
        self.assertEqual(self.post.call_count, 2)

    def test_expired_token_is_refreshed(self):
        m._TOKEN_CACHE = m._TokenCache('OLD', 'Bearer', 1)
        self.assertEqual(m.get_access_token(), 'TOKEN')
        self.post.assert_called_once()

    def test_redirect_or_error_does_not_leak_password(self):
        self.post.return_value.status_code = 302
        self.post.return_value.text = 'PRIVATE'
        with self.assertRaises(RuntimeError) as ctx:
            m.get_access_token()
        self.assertNotIn('PRIVATE', str(ctx.exception))

    def test_invalid_path_rejected_before_login(self):
        for path in ['https://other.example/path', '//other.example/path', '/../secrets']:
            with self.assertRaises(ValueError):
                m.marti_get(path)
        self.post.assert_not_called()


if __name__ == '__main__': unittest.main()
