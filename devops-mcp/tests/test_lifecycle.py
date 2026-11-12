import unittest
from unittest.mock import patch

from app import lifecycle_component as lifecycle
from app.orchestrator_component import launch_checked


class Registry:
    def __init__(self):
        self.tools = {}

    def tool(self):
        def register(fn):
            self.tools[fn.__name__] = fn
            return fn
        return register


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.node = {'node_id': 'taklabs.example.com', 'unit_path': 'taklabs',
                     'aws_instance_id': 'i-0123456789abcdef0', 'aws_state': 'running'}
        self.selection = 'fresh-backup'
        self.verified = True
        self.buckets = list(lifecycle.BUCKETS)
        def api(method, path, data=None):
            self.calls.append((method, path, data))
            if path == '/api/v2/nodes':
                return {'ok': True, 'items': [self.node], 'aws': {'instances': []}}
            if path.endswith('/restore-selection'):
                return {'ok': True, 'restore_backup': {'backup_id': self.selection}}
            if path.endswith('/verify'):
                return {'ok': True, 'verified': self.verified, 'buckets': self.buckets}
            return {'ok': True}
        self.api = api
        reg = Registry()
        lifecycle.register_lifecycle_tools(reg, api)
        self.tools = reg.tools

    def shutdown(self, **overrides):
        args = dict(node_id='taklabs.example.com', unit_path='taklabs',
                    expected_instance_id='i-0123456789abcdef0',
                    backup_id='fresh-backup', confirm_shutdown=True)
        return self.tools['taks_node_shutdown'](**(args | overrides))

    def test_mutations_require_confirmation_before_api_call(self):
        self.assertTrue(self.shutdown(confirm_shutdown=False)['confirmation_required'])
        self.assertTrue(self.tools['taks_node_backup_start']('taklabs', ['users'])['confirmation_required'])
        self.assertTrue(self.tools['taks_backup_select_restore']('taklabs', 'fresh-backup')['confirmation_required'])
        self.assertTrue(self.tools['taks_bundle_prepare_start']('taklabs', True)['confirmation_required'])
        self.assertTrue(self.tools['taks_node_launch_start']('taklabs')['confirmation_required'])
        self.assertEqual(self.calls, [])

    def test_path_injection_and_unknown_buckets_never_reach_api(self):
        for unit in ('../state', 'taklabs/../other', '/taklabs', 'taklabs?x=y'):
            self.assertFalse(self.tools['taks_backups_list'](unit)['ok'])
        self.assertFalse(self.tools['taks_node_backup_start']('../node', ['users'], True)['ok'])
        self.assertFalse(self.tools['taks_node_backup_start']('taklabs', ['arbitrary_file'], True)['ok'])
        self.assertFalse(self.tools['taks_backup_select_restore']('taklabs', '../file', True)['ok'])
        self.assertEqual(self.calls, [])

    def test_shutdown_checks_instance_selection_and_integrity_before_termination(self):
        self.assertFalse(self.shutdown(expected_instance_id='i-11111111111111111')['ok'])
        self.selection = 'old-backup'
        self.assertFalse(self.shutdown()['ok'])
        self.selection = 'fresh-backup'
        self.verified = False
        self.assertFalse(self.shutdown()['ok'])
        self.verified = True
        self.buckets = ['users']
        self.assertFalse(self.shutdown()['ok'])
        self.assertFalse(any(path.endswith('/shutdown') for _, path, _ in self.calls))
        self.buckets = list(lifecycle.BUCKETS)
        self.assertTrue(self.shutdown()['ok'])
        self.assertTrue(self.calls[-1][1].endswith('/shutdown'))

    def test_backup_is_polled_and_failure_is_visible(self):
        result = self.tools['taks_node_backup_start']('taklabs', ['users', 'certs'], True)
        lifecycle.JOBS[result['operation_id']][1].result(timeout=2)
        status = self.tools['taks_operation_status'](result['operation_id'])
        self.assertEqual(status['status'], 'done')
        self.assertTrue(status['result']['ok'])
        self.assertEqual(self.calls[-1], ('POST', '/api/v2/nodes/taklabs/backup', {'buckets': ['users', 'certs']}))
        self.assertEqual(self.tools['taks_operation_status']('unknown')['status'], 'unknown')

    def test_concurrent_duplicate_operation_returns_same_id(self):
        from concurrent.futures import Future
        future = Future()
        with patch.object(lifecycle.POOL, 'submit', return_value=future):
            first = lifecycle.submit(('test', 'same'), lambda: None)
            second = lifecycle.submit(('test', 'same'), lambda: None)
        self.assertEqual(first['operation_id'], second['operation_id'])
        future.set_result({'ok': True})

    def test_launch_uses_aws_state_instead_of_orphaned_registry(self):
        calls = []
        def api(method, path, data=None):
            calls.append(path)
            return {'ok': True, 'orphaned_items': [self.node], 'aws': {'instances': []}}
        self.assertTrue(launch_checked('taklabs', api_call=api)['ok'])
        self.assertEqual(calls[-1], '/api/v2/nodes/launch')
        for inventory in ({'ok': False}, {'items': []}, {'aws': {'instances': [{'unit_path': 'taklabs', 'state': 'running'}]}}):
            calls.clear()
            def blocked(method, path, data=None):
                calls.append(path)
                return inventory
            self.assertFalse(launch_checked('taklabs', api_call=blocked)['ok'])
            self.assertEqual(calls, ['/api/v2/nodes'])

    def test_server_catalog_registers_lifecycle_tools(self):
        from app.server import mcp
        import asyncio
        names = {t.name for t in asyncio.run(mcp.list_tools())}
        self.assertTrue(set(self.tools).issubset(names))
