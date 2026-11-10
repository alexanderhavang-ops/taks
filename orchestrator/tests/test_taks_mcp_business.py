"""Domain boundary tests for the TAKS business MCP."""
import unittest
from taks_mcp.business import register_taks_tools


class Registry:
    def __init__(self):
        self.tools = {}

    def tool(self):
        def register(fn):
            self.tools[fn.__name__] = fn
            return fn
        return register


class BusinessTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.state = "running"
        def api(method, path, data=None):
            self.calls.append((method, path))
            if path == "/api/v2/nodes":
                return {"items": [{"node_id": "49hvbat", "aws_state": self.state}]}
            if path == "/api/v2/nodes/preview":
                return {"plan": {"role": "tak-node"}}
            return {"ok": True}
        self.registry = Registry()
        register_taks_tools(self.registry, api)

    def test_no_devops_tools(self):
        self.assertFalse(any(name.startswith(("fs_", "host_", "aws_", "daemon_"))
                             for name in self.registry.tools))






    def test_business_catalog_excludes_deployment_and_filesystem_mutations(self):
        for name in ('taks_node_devops_probe','taks_node_launch','taks_node_shutdown','taks_bundle_build','fs_write','deploy_orchestrator'):
            self.assertNotIn(name,self.registry.tools)
        self.assertEqual(self.calls,[])

    def test_health_works_when_devops_is_absent(self):
        def api(method,path,data=None):
            self.assertNotIn('/mcp/devops',path)
            if path == '/api/v2/nodes':
                return {'items':[{'node_id':'49hvbat','aws_state':'running','status':'online'}]}
            return {'result':{'tools':[],'content':[]}}
        registry=Registry();register_taks_tools(registry,api)
        self.assertTrue(registry.tools['taks_node_health']('49hvbat')['ok'])

    def test_business_health_includes_shared_takserver_readiness(self):
        def api(method, path, data=None):
            if path == "/api/v2/nodes":
                return {"items": [{"node_id": "49hvbat", "aws_state": "running",
                                   "status": "online", "checks": {}}]}
            if data and data.get("method") == "tools/list":
                return {"result": {"tools": []}}
            if data and data.get("params", {}).get("name") == "product_health":
                return {"result": {"content": [{"type": "text", "text": "ready"}]}}
            return {"result": {}}
        registry = Registry()
        register_taks_tools(registry, api)
        result = registry.tools["taks_node_health"]("49hvbat")
        self.assertIn("takserver_readiness", result)
        self.assertNotIn("netstat_listeners", result)








    def test_business_write_requires_explicit_confirmation(self):
        result = self.registry.tools["taks_node_create_user"](
            "taklabs.aws.example.com", "alex", "alex@example.com")
        self.assertTrue(result["confirmation_required"])
        self.assertEqual(self.calls, [])
        result = self.registry.tools["taks_node_send_invite"](
            "taklabs.aws.example.com", "alex", "alex@example.com")
        self.assertTrue(result["confirmation_required"])
        self.assertEqual(self.calls, [])

    def test_business_create_and_invite_use_taks_not_devops_bridge(self):
        responses = {"onboarding_user_create": {"ok": True, "username": "alex"},
                     "onboarding_send_invite": {"ok": True, "delivery": "resend"}}
        calls = []
        def api(method, path, data=None):
            calls.append((method, path, data))
            action = data["params"]["name"]
            return {"jsonrpc": "2.0", "id": 1, "result": {
                "content": [{"type": "text", "text": __import__("json").dumps(responses[action])}]}}
        reg = Registry()
        register_taks_tools(reg, api)
        node = "taklabs.aws.example.com"
        create = reg.tools["taks_node_create_user"](
            node, "alex", "alex@example.com", "Alex", "testers", True)
        invite = reg.tools["taks_node_send_invite"](
            node, "alex", "alex@example.com", True)
        self.assertTrue(create["ok"])
        self.assertTrue(invite["ok"])
        self.assertEqual(len(calls), 2)
        self.assertTrue(all(path.endswith("/mcp/taks") for _, path, _ in calls))
        self.assertEqual(calls[0][2]["params"]["arguments"]["group"], "testers")
        self.assertNotIn("card_url", invite)
        self.assertNotIn("password", create)

    def test_business_proxy_rejects_bad_ids_and_emails(self):
        action = self.registry.tools["taks_node_create_user"]
        self.assertFalse(action("../shadow", "alex", "alex@example.com", confirm_create=True)["ok"])
        self.assertFalse(action("taklabs.aws.example.com", "alex", "invalid", confirm_create=True)["ok"])
        self.assertEqual(self.calls, [])

    def test_business_tools_discovery(self):
        result = self.registry.tools["taks_node_business_tools"]("taklabs.aws.example.com")
        self.assertTrue(result["ok"])
        self.assertTrue(self.calls[-1][1].endswith("/mcp/taks"))

if __name__ == "__main__":
    unittest.main()


class BusinessTimeoutTests(unittest.TestCase):
    def test_bundle_and_launch_requests_allow_long_operations(self):
        from unittest.mock import patch, MagicMock
        from taks_mcp import business
        for path, timeout in [("/api/v2/bundles/build", 240), ("/api/v2/bundles/readiness", 240), ("/api/v2/nodes/launch", 240), ("/api/v2/nodes", 25)]:
            response = MagicMock()
            response.__enter__.return_value.read.return_value = b'{"ok":true}'
            with self.subTest(path=path), patch("orchestrator_api.service_auth.business_service_token", return_value="test-service-token"), patch.object(business.urllib.request, "urlopen", return_value=response) as request:
                self.assertTrue(business.call("POST", path, {})["ok"])
                self.assertEqual(request.call_args.kwargs["timeout"], timeout)
