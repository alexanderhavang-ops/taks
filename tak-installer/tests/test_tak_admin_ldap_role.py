"""LDAP admin metadata must also register the Marti authorization role."""
import unittest
from pathlib import Path
from unittest.mock import patch
from tak_installer.actions import tak_admin_identity as action


class LdapAdminRoleTests(unittest.TestCase):
    def test_ldap_admin_does_not_copy_password_to_xml(self):
        with patch.object(action, '_ensure_inputs', return_value=('admin', 'PRIVATE', [], [], [])), \
             patch.object(action, 'selected_backing_user_store', return_value='ldap'), \
             patch.object(action, 'build_backing_user_store') as backing, \
             patch.object(action, 'UserMgrService') as service:
            action._bind_user_to_cert({}, {}, Path('/opt/tak/certs/admin.pem'))
        backing.return_value.ensure_user.assert_called_once()
        service.assert_not_called()


    def test_ldap_registration_failure_fails_installer(self):
        with patch.object(action, '_ensure_inputs', return_value=('admin', 'PRIVATE', [], [], [])), \
             patch.object(action, 'selected_backing_user_store', return_value='ldap'), \
             patch.object(action, 'build_backing_user_store') as backing, \
             patch.object(action, 'UserMgrService') as service:
            backing.return_value.ensure_user.side_effect = RuntimeError('LDAP registration failed')
            with self.assertRaisesRegex(RuntimeError, 'LDAP registration failed'):
                action._bind_user_to_cert({}, {}, Path('/opt/tak/certs/admin.pem'))
            service.assert_not_called()


if __name__ == '__main__': unittest.main()
