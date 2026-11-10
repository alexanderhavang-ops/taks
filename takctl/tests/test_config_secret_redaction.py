import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from takctl import config_store as store

class ConfigSecretRedactionTests(unittest.TestCase):
    def test_public_state_has_presence_without_values_and_save_retains_secret(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for name in ('conf.d','secrets.d','confmeta'):(root/name).mkdir()
            (root/'conf.d/main.conf').write_text('fqdn = unit.example\n')
            (root/'secrets.d/main.conf').write_text('openai_api_key = fixture-private-value\n')
            with patch.object(store,'RUNTIME_CONF_DIR',root/'conf.d'),patch.object(store,'RUNTIME_SECRETS_DIR',root/'secrets.d'),patch.object(store,'RUNTIME_CONFMETA_DIR',root/'confmeta'):
                result=store.runtime_public_state()
                self.assertNotIn('fixture-private-value',json.dumps(result))
                self.assertEqual(result['secrets']['openai_api_key'],'')
                self.assertTrue(result['secret_present']['openai_api_key'])
                store.apply_runtime_updates(config_updates={'fqdn':'changed.example'})
                self.assertEqual(store.load_runtime_secrets_view().get('openai_api_key'),'fixture-private-value')
