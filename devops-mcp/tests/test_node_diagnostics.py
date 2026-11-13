import json
import unittest

from app.node_diagnostics_component import register_node_diagnostics_tools, redact


class Registry:
    def tool(self):
        def register(fn):
            self.probe = fn
            return fn
        return register


class NodeDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        def api(*args):
            self.calls.append(args)
            return {'ok': True}
        registry = Registry()
        register_node_diagnostics_tools(registry, api)
        self.probe = registry.probe

    def test_invalid_operations_services_paths_and_bounds_never_reach_bridge(self):
        for args in ({'operation': 'shell_exec'}, {'node_id': '../other'},
                     {'operation': 'service_logs', 'service': 'arbitrary.service'},
                     {'operation': 'takserver_logs', 'file': '../../secrets.conf'},
                     {'operation': 'takserver_logs', 'lines': 81},
                     {'operation': 'service_status', 'service': 'nginx.service', 'file': 'other'}):
            with self.subTest(args=args):
                self.assertFalse(self.probe(**({'node_id': 'test.example.com'} | args))['ok'])
        self.assertEqual(self.calls, [])

    def test_log_discovery_and_fixed_tail_use_only_devops_domain(self):
        self.probe('test.example.com', 'takserver_logs')
        self.probe('test.example.com', 'takserver_logs', file='takserver-messaging.log', lines=20)
        method, path, rpc = self.calls[-1]
        self.assertEqual((method, path), ('POST', '/api/v2/nodes/test.example.com/mcp/devops'))
        self.assertEqual(rpc['params'], {'name': 'takserver_logs', 'arguments': {'file': 'takserver-messaging.log', 'lines': 20}})

    def test_nested_rpc_and_header_secrets_are_redacted(self):
        rpc = {'result': {'content': [{'type': 'text', 'text': json.dumps({
            'password': 'hidden-value', 'logs': 'Authorization: Bearer hidden-token\nkeystorePass="hidden-store"\nrequest failed'})}]}}
        result = json.dumps(redact(rpc))
        for value in ('hidden-value', 'hidden-token', 'hidden-store'):
            self.assertNotIn(value, result)
        self.assertIn('request failed', result)
