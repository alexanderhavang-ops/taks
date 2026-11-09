import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tak_installer.actions import openfire_server_core as action


class OpenfireRestPluginTests(unittest.TestCase):
    def test_checksum_mismatch_aborts_before_plugin_install(self):
        with patch.object(action.urllib.request, 'urlopen', return_value=io.BytesIO(b'changed')), \
             patch.object(action, '_run') as run:
            with self.assertRaisesRegex(RuntimeError, 'checksum mismatch'):
                action._ensure_rest_api_plugin()
            run.assert_not_called()


if __name__ == '__main__': unittest.main()
