import unittest
from unittest.mock import patch
from takctl.services.ldap_user_store import LdapConfig, LdapUserStore


class LdapAdminGroupTests(unittest.TestCase):
    def make_store(self):
        cfg = LdapConfig(uri='ldap://localhost', base_dn='dc=test', people_ou='people',
            groups_ou='groups', services_ou='services', bind_dn='reader', bind_password='x',
            write_dn='writer', write_password='x', admin_group='TAKS_ADMIN')
        return LdapUserStore(cfg)

    def test_admin_enters_configured_group_without_xml_password(self):
        store = self.make_store()
        with patch.object(store, 'get_user', return_value=object()), \
             patch.object(store, 'groups_for_user', return_value=[]), \
             patch.object(store, '_ldapmodify'), patch.object(store, '_set_password') as setpw, \
             patch.object(store, 'ensure_group') as ensure, patch.object(store, '_add_user_to_group') as add:
            store.ensure_user('admin', admin=True)
        ensure.assert_called_once_with('TAKS_ADMIN', initial_member_dn='uid=admin,ou=people,dc=test')
        add.assert_called_once_with('admin', 'TAKS_ADMIN')
        setpw.assert_not_called()

    def test_channel_edit_preserves_existing_admin_membership(self):
        store = self.make_store()
        with patch.object(store, 'get_user', return_value=object()), \
             patch.object(store, 'groups_for_user', return_value=['TAKS_ADMIN', 'Old']), \
             patch.object(store, '_remove_user_from_group') as remove:
            store.ensure_user('admin')
        remove.assert_called_once_with('admin', 'Old')

    def test_regular_user_does_not_receive_admin_group(self):
        store = self.make_store()
        with patch.object(store, 'get_user', return_value=object()), \
             patch.object(store, 'groups_for_user', return_value=[]), \
             patch.object(store, '_add_user_to_group') as add:
            store.ensure_user('alexander')
        add.assert_not_called()


if __name__ == '__main__': unittest.main()
