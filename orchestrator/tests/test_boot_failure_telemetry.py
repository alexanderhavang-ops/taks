import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


class BootFailureTelemetryTests(unittest.TestCase):
    def test_failed_boot_reports_traceback_without_credentials(self):
        script = Path(__file__).resolve().parents[1] / 'orchestrator_core/default_bundle/install/taks-heartbeat.sh'
        python = script.read_text().split("python3 - <<'PY'\n")[2].split('\nPY\n')[0]
        real_open = open
        secret = 'example-secret-not-for-telemetry'
        def fake_open(path, *args, **kwargs):
            if str(path) == '/var/log/cloud-init-output.log':
                return io.BytesIO(('Traceback: decoder failed\nkey=' + secret + '\npassword=another-secret\n-----BEGIN PRIVATE KEY-----\nprivate\n-----END PRIVATE KEY-----').encode())
            return real_open(path, *args, **kwargs)
        with tempfile.TemporaryDirectory() as tmp:
            events = Path(tmp) / 'events'
            events.write_text('takserver,2026-11-09T16:59:00Z,Started\ninstall/main,2026-11-09T17:00:00Z,Failed\n')
            output = io.StringIO()
            with patch.dict(os.environ, {'INSTALL_STATE_LOG': str(events), 'NODE_HEALTH_JSON': '/nonexistent'}), patch('builtins.open', side_effect=fake_open), patch.object(Path, 'glob', return_value=[SimpleNamespace(read_text=lambda: 'api_key=' + secret)]), contextlib.redirect_stdout(output):
                exec(compile(python, '<heartbeat>', 'exec'), {})
            result = json.loads(output.getvalue())
            self.assertEqual(result['install']['summary']['state'], 'failed')
            tail = result['install']['diagnostics']['tail']
            self.assertIn('Traceback: decoder failed', tail)
            self.assertNotIn(secret, tail)
            self.assertNotIn('another-secret', tail)
            self.assertNotIn('BEGIN PRIVATE KEY', tail)
            self.assertLessEqual(len(tail), 24000)


if __name__ == '__main__':
    unittest.main()
