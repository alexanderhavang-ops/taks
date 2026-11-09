"""LDAP admin metadata must also register the Marti authorization role."""
import unittest
from pathlib import Path
from unittest.mock import patch
from tak_installer.actions import tak_admin_identity as action


class LdapAdminRoleTests(unittest.TestCase):
    def test_ldap_admin_also_has_tak_authorization_record(self):
        with patch.object(action, '_ensure_inputs', return_value=('admin', 'PRIVATE', [], [], [])), \
             patch.object(action, 'selected_backing_user_store', return_value='ldap'), \
             patch.object(action, 'build_backing_user_store') as backing, \
             patch.object(action, 'UserMgrService') as service:
            action._bind_user_to_cert({}, {}, Path('/opt/tak/certs/admin.pem'))
        backing.return_value.ensure_user.assert_called_once()
        service.return_value.preflight.assert_called_once()
        service.return_value.user_set.assert_called_once_with(
            'admin', password='PRIVATE', admin=True,
            certificate_path='/opt/tak/certs/admin.pem',
            groups=None, in_groups=None, out_groups=None)

    def test_role_registration_failure_fails_installer(self):
        with patch.object(action, '_ensure_inputs', return_value=('admin', 'PRIVATE', [], [], [])), \
             patch.object(action, 'selected_backing_user_store', return_value='ldap'), \
             patch.object(action, 'build_backing_user_store'), \
             patch.object(action, 'UserMgrService') as service:
            service.return_value.user_set.side_effect = RuntimeError('role registration failed')
            with self.assertRaisesRegex(RuntimeError, 'role registration failed'):
                action._bind_user_to_cert({}, {}, Path('/opt/tak/certs/admin.pem'))


if __name__ == '__main__':
    unittest.main()
