"""Service-native integration gates using disposable objects and guaranteed cleanup."""
import os
import unittest
import uuid
from takctl.services.business_services import call
from takctl.services.ldap_user_store import LdapUserStore


@unittest.skipUnless(os.environ.get('TAKS_SERVICE_LIVE_TESTS') == '1', 'requires installed native services')
class LiveBusinessServices(unittest.TestCase):
    def check(self, service, operation, args, write=False):
        result = call(service, operation, args, write=write, confirm_write=write)
        self.assertTrue(result.get('ok'), str(result))
        return result

    def test_ldap_group_round_trip(self):
        name = 'MCPTest' + uuid.uuid4().hex[:10]
        self.check('ldap', 'group_create', {'group': name}, True)
        try:
            store = LdapUserStore()
            result = store._ldapsearch(store.config.group_dn(name), '(objectClass=*)', ('dn',))
            self.assertIn('dn:', result)
        finally:
            self.check('ldap', 'group_delete', {'group': name}, True)

    def test_mumble_channel_round_trip(self):
        self.check('mumble', 'snapshot', {})
        name = 'MCPTest' + uuid.uuid4().hex[:10]
        result = self.check('mumble', 'channel_create', {'name': name, 'parent': 0}, True)
        channel_id = result['data']['channel_id']
        try:
            self.check('mumble', 'channel_rename', {'channel_id': channel_id, 'name': name + 'Renamed'}, True)
            channels = self.check('mumble', 'snapshot', {})['data']['channels']
            self.assertTrue(any(c['id'] == channel_id and c['name'] == name + 'Renamed' for c in channels))
        finally:
            self.check('mumble', 'channel_delete', {'channel_id': channel_id}, True)

    def test_openfire_room_round_trip(self):
        self.check('openfire', 'sessions', {})
        room = 'mcptest' + uuid.uuid4().hex[:10]
        self.check('openfire', 'room_create', {'room': room}, True)
        try:
            self.check('openfire', 'room_subject_set', {'room': room, 'subject': 'MCP integration test'}, True)
            data = self.check('openfire', 'room', {'room': room})['data']
            self.assertEqual(data['subject'], 'MCP integration test')
        finally:
            self.check('openfire', 'room_delete', {'room': room}, True)


if __name__ == '__main__': unittest.main()
