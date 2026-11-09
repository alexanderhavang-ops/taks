"""Live post-install gate for LDAP OAuth roles; no messages or user mutations."""
import os
from pathlib import Path
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
from takctl.config import load_config, load_secrets
from takctl.services import marti_api as m


@unittest.skipUnless(os.environ.get('TAKS_MARTI_LIVE_TESTS') == '1', 'requires installed TAK node')
class LiveMartiOAuthTests(unittest.TestCase):
    def test_installer_admin_can_read_protected_marti_inputs(self):
        response = m.marti_get('/Marti/api/inputs', force_refresh=True)
        self.assertEqual(response.status_code, 200, 'LDAP OAuth admin cannot read protected Marti inputs')
        response.json()

    def test_martine_identity_cannot_read_protected_marti_inputs(self):
        cfg, sec = load_config(), load_secrets()
        user = str(cfg.get('martine_username', 'martine') or 'martine')
        password = str(sec.get('martine_user_password', '') or '')
        self.assertTrue(password, 'Missing ordinary Martine LDAP credential')
        try:
            with patch.object(m, '_credentials', return_value=(user, password)):
                response = m.marti_get('/Marti/api/inputs', force_refresh=True)
            self.assertEqual(response.status_code, 403, 'Ordinary Martine identity has administrator access')
        finally:
            m._TOKEN_CACHE = m._TokenCache()

    def test_admin_password_has_no_xml_copy(self):
        path = Path('/opt/tak/UserAuthenticationFile.xml')
        if path.exists():
            username = str(load_config().get('takctl_admin_user', 'admin') or 'admin')
            for user in ET.parse(path).getroot().iter():
                if user.tag.rsplit('}', 1)[-1] == 'User' and user.get('identifier') == username:
                    self.assertFalse(user.get('password'), 'LDAP admin password duplicated in XML')


if __name__ == '__main__': unittest.main()
