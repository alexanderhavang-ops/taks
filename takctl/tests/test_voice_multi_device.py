from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

SCRIPT = Path(__file__).resolve().parents[2] / 'takctl/bin/taks-mumble-voice-pin-auth.py'


class VoiceMultiDeviceTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.addCleanup(self.db.close)
        self.db.execute('CREATE TABLE client_endpoint(uid TEXT, username TEXT)')
        self.db.executemany('INSERT INTO client_endpoint VALUES(?,?)',
            [('phone-one', 'alexander'), ('phone-two', 'alexander'), ('other-phone', 'bob')])
        self.ns = {'__name__': 'test_multi_device_auth'}
        with patch.dict(sys.modules, {'Ice': SimpleNamespace(loadSlice=lambda _: None),
             'MumbleServer': SimpleNamespace(ServerAuthenticator=object)}):
            exec(compile(SCRIPT.read_text(), str(SCRIPT), 'exec'), self.ns)
        def run(command, **kwargs):
            rows = self.db.execute(command[-1].replace('public.client_endpoint', 'client_endpoint')).fetchall()
            return SimpleNamespace(returncode=0, stdout='\n'.join('\t'.join(row) for row in rows))
        self.ns['subprocess'] = SimpleNamespace(run=run, PIPE=-1, DEVNULL=-3)
        self.ns['log'] = lambda _: None
        self.ns['save_state'] = Mock()
        self.ns['recent_takserver_seen'] = Mock(return_value=(True, 'active TAK presence'))
        self.state = {'records': {'ALEXANDER': {'uid': 'phone-one', 'enabled': True}}}
        self.ns['load_state'] = lambda: self.state
        self.ns['x509_summary_from_der'] = lambda der: {'cn': der.decode()}
        self.auth = self.ns['VoicePinAuthenticator']()

    def connect(self, uid):
        return self.auth.authenticate('Alexander---' + uid, '', [uid.encode()], '', False)

    def test_both_phones_on_same_account_can_authenticate_without_replacing_primary_binding(self):
        first = self.connect('phone-one')
        second = self.connect('phone-two')
        self.assertGreater(first[0], 0)
        self.assertGreater(second[0], 0)
        self.assertNotEqual(first[0], second[0])
        self.assertEqual(self.state['records']['ALEXANDER']['uid'], 'phone-one')
        self.assertEqual({row['uid'] for row in self.state['records']['ALEXANDER']['mumble_identities'].values()}, {'phone-one', 'phone-two'})

    def test_matching_callsign_does_not_authorize_other_accounts_or_unknown_uids(self):
        self.assertEqual(self.connect('other-phone')[0], -1)
        self.assertEqual(self.connect('unknown-phone')[0], -1)

    def test_ambiguous_device_owner_is_rejected(self):
        self.db.execute("INSERT INTO client_endpoint VALUES('phone-two','bob')")
        self.assertEqual(self.connect('phone-two')[0], -1)

    def test_same_account_still_requires_tak_presence(self):
        self.ns['recent_takserver_seen'].return_value = (False, 'not connected')
        self.assertEqual(self.connect('phone-two')[0], -1)

    def test_disabled_profile_remains_disabled_for_every_phone(self):
        self.state['records']['ALEXANDER']['enabled'] = False
        self.assertEqual(self.connect('phone-one')[0], -1)
        self.assertEqual(self.connect('phone-two')[0], -1)

    def test_ownership_lookup_failure_fails_closed(self):
        self.ns['subprocess'].run = Mock(side_effect=OSError('database unavailable'))
        self.assertEqual(self.connect('phone-two')[0], -1)
