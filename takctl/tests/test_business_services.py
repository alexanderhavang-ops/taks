import io
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from takctl.services import business_services as b
from takctl.services.mumble_ice_worker import invoke
from takctl.web.mcp_domains import taks


class ServiceBusinessTests(unittest.TestCase):
    def test_write_requires_confirmation_before_native_call(self):
        for service, operation in [('ldap', 'group_create'), ('mumble', 'channel_create'), ('openfire', 'room_create')]:
            with patch.object(b, '_ldap') as ldap, patch.object(b, '_mumble') as mumble, patch.object(b, '_openfire_operation') as openfire:
                result = b.call(service, operation, {}, write=True)
                self.assertTrue(result['confirmation_required'])
                for mock in (ldap, mumble, openfire): mock.assert_not_called()

    def test_no_arbitrary_paths_commands_or_cross_domain_writes(self):
        for service, operation, args in [('ssh', 'exec', {}), ('ldap', 'group_delete', {}),
                                         ('openfire', 'sessions', {'url': 'https://elsewhere'}),
                                         ('mumble', 'snapshot', {'command': 'id'})]:
            with self.assertRaises(ValueError): b.call(service, operation, args)
        with self.assertRaises(ValueError): b.call([], 'snapshot', {})

    def test_node_business_tool_dispatches_confirmed_write(self):
        with patch.object(b, '_ldap', return_value={'ok': True}) as backend:
            result = taks.call('service_write', {'service': 'ldap', 'operation': 'group_create',
                'arguments': {'group': 'Blue'}, 'confirm_write': True})
        self.assertTrue(json.loads(result['content'][0]['text'])['ok'])
        backend.assert_called_once_with('group_create', {'group': 'Blue'})

    def test_ldap_write_uses_existing_directory_and_never_resets_password(self):
        with patch.object(b, 'LdapUserStore') as factory:
            store = factory.return_value
            store.get_user.return_value = object()
            store.groups_for_user.return_value = ['Blue']
            self.assertTrue(b.call('ldap', 'user_groups_set', {'username': 'alex', 'groups': ['Blue']}, write=True, confirm_write=True)['ok'])
            store.ensure_user.assert_called_once_with('alex', groups=['Blue'])

    def test_admin_group_cannot_be_deleted(self):
        with patch.object(b, 'LdapUserStore') as factory:
            factory.return_value.config.admin_group = 'TAKS_ADMIN'
            with self.assertRaises(ValueError):
                b.call('ldap', 'group_delete', {'group': 'TAKS_ADMIN'}, write=True, confirm_write=True)
            factory.return_value._ldapdelete.assert_not_called()

    def test_mumble_worker_is_fixed_and_root_channel_protected(self):
        with patch.object(b.subprocess, 'run', return_value=SimpleNamespace(stdout='{"ok":true}')) as run:
            self.assertTrue(b.call('mumble', 'snapshot', {})['ok'])
            self.assertEqual(run.call_args.args[0][:2], ['/usr/bin/python3', '-I'])
            self.assertNotIn('shell', run.call_args.kwargs)
            with self.assertRaises(ValueError):
                b.call('mumble', 'channel_delete', {'channel_id': 0}, write=True, confirm_write=True)
            self.assertEqual(run.call_count, 1)

    def test_mumble_native_channel_writes(self):
        server = Mock()
        server.addChannel.return_value = 7
        self.assertEqual(invoke(server, 'channel_create', {'name': 'Test', 'parent': 0}), {'channel_id': 7})
        channel = SimpleNamespace(id=7, name='Test')
        server.getChannelState.return_value = channel
        invoke(server, 'channel_rename', {'channel_id': 7, 'name': 'Updated'})
        self.assertEqual(channel.name, 'Updated')
        invoke(server, 'channel_delete', {'channel_id': 7})
        server.removeChannel.assert_called_once_with(7)

    def test_openfire_room_write_preserves_protected_settings(self):
        room = {'roomName': 'ops', 'password': 'PRIVATE', 'membersOnly': True}
        with patch.object(b, '_openfire', side_effect=[{'ok': True, 'data': room}, {'ok': True}]) as http:
            self.assertTrue(b.call('openfire', 'room_subject_set', {'room': 'ops', 'subject': 'Updated'}, write=True, confirm_write=True)['ok'])
        self.assertEqual(http.call_args.args[2]['password'], 'PRIVATE')
        self.assertTrue(http.call_args.args[2]['membersOnly'])

    def test_read_output_redacts_credentials(self):
        with patch.object(b, '_openfire_operation', return_value={'ok': True, 'password': 'PRIVATE', 'nested': {'secret': 'PRIVATE'}}):
            self.assertNotIn('PRIVATE', json.dumps(b.call('openfire', 'rooms', {})))

    def test_path_injection_rejected(self):
        with self.assertRaises(ValueError):
            b.call('openfire', 'room', {'room': '../system/properties'})


if __name__ == '__main__': unittest.main()
