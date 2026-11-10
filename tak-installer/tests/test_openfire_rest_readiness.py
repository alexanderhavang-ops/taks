"""Exercise the production startup wait without importing installer dependencies."""
import ast
from pathlib import Path
import types
import unittest

SOURCE = Path(__file__).parents[1] / 'tak_installer/actions/openfire_server_core.py'


class OpenfireReadinessTests(unittest.TestCase):
    def load_wait(self):
        source = ast.parse(SOURCE.read_text())
        function = next(n for n in source.body if isinstance(n, ast.FunctionDef) and n.name == '_wait_for_rest_api')
        self.now = 0
        def sleep(seconds):
            self.now += seconds
        namespace = {'time': types.SimpleNamespace(monotonic=lambda: self.now, sleep=sleep)}
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(SOURCE), 'exec'), namespace)
        return namespace['_wait_for_rest_api']

    def test_waits_through_jetty_and_plugin_startup(self):
        wait = self.load_wait()
        responses = iter([{'ok': False}, {'ok': False, 'http_status': 404}, {'ok': True}])
        wait(probe=lambda: next(responses))
        self.assertEqual(self.now, 4)

    def test_never_ready_fails_instead_of_running_integration_gate(self):
        wait = self.load_wait()
        with self.assertRaisesRegex(RuntimeError, 'did not become ready'):
            wait(timeout_s=6, probe=lambda: {'ok': False})
        self.assertEqual(self.now, 6)

    def test_service_action_waits_after_final_start(self):
        source = SOURCE.read_text()
        self.assertLess(source.rindex('_run(["sudo", "systemctl", "start", SERVICE])'), source.rindex('_wait_for_rest_api()'))
        self.assertLess(source.rindex('_wait_for_rest_api()'), source.rindex('final_active ='))
