import io
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import zipfile
from fastapi import Request
from takctl.onboarding import atak, atak_autoenroll
from takctl.onboarding.policy import Identity


class ConfiguredCallsignTests(unittest.TestCase):
    def test_auto_enroll_zip_uses_saved_user_callsign_instead_of_unit(self):
        request = Request({'type':'http', 'method':'GET', 'path':'/', 'headers':[(b'host',b'taklabs.example')], 'query_string':b''})
        for stored_callsign, expected in [('alexander','alexander'),('Alexander','Alexander'),('', 'taklabs')]:
            with self.subTest(stored_callsign=stored_callsign), tempfile.TemporaryDirectory() as tmp:
                policy = SimpleNamespace(resolve_identity=lambda ctx: Identity(callsign='taklabs',team='Blue'), meta=lambda: {})
                service = SimpleNamespace(store=SimpleNamespace(get_identity=lambda username: SimpleNamespace(identity={'callsign':stored_callsign})))
                with patch.object(atak,'load_selection',return_value={'ctx':{'unit':'taklabs','policy_id':'fro'}}), patch.object(atak,'Policy',return_value=policy), patch('takctl.onboarding.policy_registry.default_policy_id',return_value='fro'), patch('takctl.onboarding.service_builder.build_service',return_value=service), patch.object(atak_autoenroll,'load_config',return_value={}), patch.object(atak_autoenroll,'_auto_enroll_policy',return_value={'include_truststore':False,'include_truststore_password':False}):
                    output = Path(tmp) / 'package.zip'
                    atak_autoenroll.write_atak_auto_enroll_package_zip(output, 'alexander', request, False, 'https://taklabs.example')
                with zipfile.ZipFile(output) as archive:
                    root = ET.fromstring(archive.read('certs/config.pref'))
                    entries = {entry.get('key'):entry.text for entry in root.iter('entry')}
                self.assertEqual(entries['locationCallsign'], expected)
                self.assertEqual(entries['locationTeam'], 'Blue')
                self.assertEqual(entries['connectString0'], 'taklabs.example:8089:ssl')


if __name__ == '__main__':
    unittest.main()
