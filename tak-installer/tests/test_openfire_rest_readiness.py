"""Exercise the production startup wait without importing installer dependencies."""
import ast
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import types
import unittest

SOURCE = Path(__file__).parents[1] / 'tak_installer/actions/openfire_server_core.py'


class OpenfireReadinessTests(unittest.TestCase):
    def functions(self, names, **namespace):
        source = ast.parse(SOURCE.read_text())
        functions = [n for n in source.body if isinstance(n, ast.FunctionDef) and n.name in names]
        exec(compile(ast.Module(body=functions, type_ignores=[]), str(SOURCE), 'exec'), namespace)
        return namespace

    def test_schema_readiness_accepts_initial_log_and_checkpointed_tables(self):
        for storage in ('', 'MEMORY ', 'CACHED '):
            for suffix in ('.script', '.log'):
                with self.subTest(storage=storage, suffix=suffix), tempfile.TemporaryDirectory() as tmp:
                    db = Path(tmp) / 'openfire.script'
                    ns = self.functions({'_database_schema_ready'}, EMBEDDED_DB_SCRIPT=db, re=re)
                    path = db.with_suffix(suffix)
                    path.write_text('CREATE TABLE OFPROPERTY(NAME VARCHAR(100))\n')
                    self.assertFalse(ns['_database_schema_ready']())
                    path.write_text('\n'.join('CREATE ' + storage + 'TABLE PUBLIC.' + t + '(ID INT)' for t in ('OFPROPERTY', 'OFUSER', 'OFMUCROOM', 'OFMUCSERVICE')))
                    self.assertTrue(ns['_database_schema_ready']())

    def test_setup_flag_alone_never_stops_initial_database_creation(self):
        self.now = 0
        def sleep(seconds):
            self.now += seconds
        clock = types.SimpleNamespace(monotonic=lambda: self.now, sleep=sleep)
        ns = self.functions({'_wait_for_setup_complete'}, time=clock,
                            _setup_complete=lambda: True,
                            _database_schema_ready=lambda: self.now >= 4,
                            _bootstrap_console_ready=lambda: self.now >= 6)
        self.assertTrue(ns['_wait_for_setup_complete'](timeout_s=10))
        self.assertEqual(self.now, 6)
        ns['_database_schema_ready'] = lambda: False
        self.assertFalse(ns['_wait_for_setup_complete'](timeout_s=4))

    def test_actual_embedded_repairs_handle_checkpointed_hsql_schema(self):
        for storage in ('', 'MEMORY ', 'CACHED '):
            with self.subTest(storage=storage), tempfile.TemporaryDirectory() as tmp:
                db = Path(tmp) / 'openfire.script'
                db.write_text('\n'.join('CREATE ' + storage + 'TABLE PUBLIC.' + t + '(ID INT)' for t in ('OFPROPERTY', 'OFMUCROOM', 'OFMUCSERVICE')) + "\nINSERT INTO OFMUCSERVICE VALUES(1,'conference','Public Chatrooms',0)\nINSERT INTO OFID VALUES(27,1)\n")
                def run(command):
                    return subprocess.run([sys.executable, command[-1]], capture_output=True, text=True, check=True)
                ns = self.functions({'_ensure_embedded_db_auth_provider_consistency', '_ensure_embedded_db_muc_rooms'},
                                    EMBEDDED_DB_SCRIPT=db, Path=Path, os=os, json=json, _run=run,
                                    _desired_conference_rooms=lambda cfg: [{'local':'org-test', 'natural':'Org-test'}])
                self.assertTrue(ns['_ensure_embedded_db_auth_provider_consistency']({'backing_user_store':'ldap'}))
                self.assertTrue(ns['_ensure_embedded_db_muc_rooms']({}))
                result = db.read_text()
                self.assertIn("'provider.auth.className'", result)
                self.assertIn("'org-test'", result)
                self.assertGreater(result.index('INSERT INTO OFPROPERTY'), result.index('TABLE PUBLIC.OFPROPERTY'))

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
