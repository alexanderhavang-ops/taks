import ast
import json
from pathlib import Path
import re
import sqlite3
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[2]
AUTH = ROOT / 'takctl/bin/taks-mumble-voice-pin-auth.py'
INSTALLER = ROOT / 'tak-installer/tak_installer/actions/mumble_server_core.py'


def functions(path, names, globals):
    tree = ast.parse(path.read_text())
    code = ast.Module(body=[node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names], type_ignores=[])
    exec(compile(code, str(path), 'exec'), globals)
    return globals


class VoiceIdentityTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.db.execute('CREATE TABLE client_endpoint(id INTEGER, callsign TEXT, uid TEXT, username TEXT)')
        self.db.execute("INSERT INTO client_endpoint VALUES(1, 'alexander', 'ANDROID-correct', 'alexander')")
        def run(command, **kwargs):
            rows = self.db.execute(command[-1].replace('public.client_endpoint','client_endpoint')).fetchall()
            return SimpleNamespace(returncode=0, stdout='\n'.join(row[0] for row in rows))
        self.env = functions(AUTH, {'lookup_takserver_uid_for_callsign','backfill_record_from_takserver','_sync_voice_specs'}, {'Any':object,'subprocess':SimpleNamespace(run=run, PIPE=-1, DEVNULL=-3), 'json':json, 'log':lambda *args:None,'save_state':Mock(),'iso_now':lambda:'now'})

    def tearDown(self):
        self.db.close()

    def test_mixed_case_callsigns_resolve_to_same_exact_uid(self):
        for callsign in ['alexander','Alexander','ALEXANDER']:
            self.assertEqual(self.env['lookup_takserver_uid_for_callsign'](callsign), 'ANDROID-correct')

    def test_case_insensitive_lookup_does_not_accept_another_device_uid(self):
        state={'records':{}}
        result = self.env['backfill_record_from_takserver'](state, state['records'], 'Alexander', 'ANDROID-impostor')
        self.assertEqual(result,{})
        self.env['save_state'].assert_not_called()
        accepted = self.env['backfill_record_from_takserver'](state,state['records'],'Alexander','ANDROID-correct')
        self.assertEqual(accepted['uid'],'ANDROID-correct')

    def test_martine_registration_is_consumed_by_canonical_authenticator(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'onboarding';folder.mkdir()
            (folder/'voice_spec.json').write_text(json.dumps({'target':{'callsign':'alexander','uid':'ANDROID-correct'}}))
            self.env['VOICE_ONBOARDING_ROOT']=Path(tmp)
            result=self.env['_sync_voice_specs']({'records':{}})
            self.assertEqual(result['records']['ALEXANDER']['uid'],'ANDROID-correct')

    def test_missing_secret_files_do_not_enable_a_builtin_service_password(self):
        from unittest.mock import patch
        env = functions(AUTH, {'load_service_passwords'}, {'Path':Path,'SERVICE_PASSWORD_FILE':Path('/missing/service-password')})
        with patch.object(Path, 'read_text', side_effect=FileNotFoundError):
            self.assertEqual(env['load_service_passwords'](),set())

    def test_installer_uses_the_canonical_file_instead_of_an_embedded_copy(self):
        install=Mock()
        env=functions(INSTALLER, {'_install_voice_authenticator'}, {'Context':object,'AUTH_BIN':Path('/runtime/auth.py'),'AUTH_UNIT':Path('/systemd/auth.service'),'_run':Mock(),'_sudo_install_text':install,'_auth_unit_text':lambda:'unit'})
        env['_install_voice_authenticator'](SimpleNamespace(repo_root=ROOT))
        self.assertEqual(install.call_args_list[0].args[1],AUTH.read_text())
        self.assertNotIn('AUTH_SCRIPT =', INSTALLER.read_text())


if __name__ == '__main__':
    unittest.main()
