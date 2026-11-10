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

    def test_node_devops_probe_is_read_only(self):
        probe = self.registry.tools["taks_node_devops_probe"]
        self.assertEqual(probe("49hvbat", "tools/list"), {"ok": True})
        self.assertEqual(self.calls[-1], ("POST", "/api/v2/nodes/49hvbat/mcp/devops"))
        self.assertEqual(probe("49hvbat", "host_identity"), {"ok": True})
        self.assertFalse(probe("49hvbat", "tools/call")["ok"])
        self.assertFalse(probe("../bad", "tools/list")["ok"])

    def test_node_devops_operations_are_bounded(self):
        probe = self.registry.tools["taks_node_devops_probe"]
        self.assertFalse(probe("49hvbat", "shell_exec")["ok"])
        self.assertFalse(probe("49hvbat", "service_status", service="sshd.service")["ok"])
        self.assertFalse(probe("49hvbat", "file_stat", path="/etc/shadow")["ok"])
        self.assertFalse(probe("49hvbat", "installer_tail", lines=10000)["ok"])
        self.assertEqual(probe("49hvbat", "service_logs", service="takserver.service")["ok"], True)

    def test_confirmation_required(self):
        result = self.registry.tools["taks_node_snooze"]("49hvbat")
        self.assertTrue(result["confirmation_required"])
        self.assertFalse(self.calls)

    def test_stop_and_wake(self):
        self.assertTrue(self.registry.tools["taks_node_snooze"]("49hvbat", True)["ok"])
        self.assertEqual(self.calls[-1], ("POST", "/api/v2/nodes/49hvbat/pause"))
        self.state = "stopped"
        self.assertTrue(self.registry.tools["taks_node_wake"]("49hvbat", True)["ok"])

    def test_node_health_probes_only_online_running_node(self):
        def api(method, path, data=None):
            self.calls.append((method, path))
            if path == "/api/v2/nodes":
                return {"items": [{"node_id": "49hvbat", "aws_state": "running",
                                   "status": "online", "checks": {}}]}
            if path.endswith("/mcp/devops"):
                if data["method"] == "tools/list":
                    return {"jsonrpc": "2.0", "id": 1, "result": {"tools": [{"name": "host_identity"}]}}
                return {"jsonrpc": "2.0", "id": 2, "result": {"content": []}}
            return {"ok": True}
        registry = Registry()
        register_taks_tools(registry, api)
        result = registry.tools["taks_node_health"]("49hvbat")
        self.assertIn("host_identity", str(result["devops_mcp"]))
        self.assertEqual(self.calls[-1], ("POST", "/api/v2/nodes/49hvbat/mcp/devops"))

    def test_business_health_includes_shared_takserver_readiness(self):
        def api(method, path, data=None):
            if path == "/api/v2/nodes":
                return {"items": [{"node_id": "49hvbat", "aws_state": "running",
                                   "status": "online", "checks": {}}]}
            if data and data.get("method") == "tools/list":
                return {"result": {"tools": []}}
            if data and data.get("params", {}).get("name") == "takserver_readiness":
                return {"result": {"content": [{"type": "text", "text": "ready"}]}}
            return {"result": {}}
        registry = Registry()
        register_taks_tools(registry, api)
        result = registry.tools["taks_node_health"]("49hvbat")
        self.assertIn("takserver_readiness", result)
        self.assertNotIn("netstat_listeners", result)

    def test_named_pause_and_resume(self):
        paused = self.registry.tools["taks_node_pause"]("49hvbat", True)
        self.assertTrue(paused["ok"])
        self.assertEqual(self.calls[-1], ("POST", "/api/v2/nodes/49hvbat/pause"))
        self.state = "stopped"
        resumed = self.registry.tools["taks_node_resume"]("49hvbat", True)
        self.assertTrue(resumed["ok"])
        self.assertEqual(self.calls[-1], ("POST", "/api/v2/nodes/49hvbat/resume"))

    def test_permanent_shutdown_requires_confirmation(self):
        result = self.registry.tools["taks_node_shutdown"]("49hvbat")
        self.assertTrue(result["confirmation_required"])
        self.assertFalse(self.calls)

    def test_permanent_shutdown_uses_terminate_not_pause(self):
        result = self.registry.tools["taks_node_shutdown"]("49hvbat", True)
        self.assertTrue(result["ok"])
        self.assertEqual(self.calls[-1], ("POST", "/api/v2/nodes/49hvbat/shutdown"))

    def test_paused_node_can_resume_but_not_pause_again(self):
        self.state = "stopped"
        result = self.registry.tools["taks_node_snooze"]("49hvbat", True)
        self.assertFalse(result["ok"])
        result = self.registry.tools["taks_node_wake"]("49hvbat", True)
        self.assertTrue(result["ok"])
        self.assertEqual(self.calls[-1], ("POST", "/api/v2/nodes/49hvbat/resume"))

    def test_launch_delegates_duplicate_validation_to_aws_aware_api(self):
        # The old instance may still have a stale local record after termination.
        # Only the REST API's fresh AWS inventory can decide if new Launch is safe.
        self.state = "terminated"
        result = self.registry.tools["taks_node_launch"]("49hvbat", True)
        self.assertTrue(result["ok"])
        self.assertEqual(self.calls[-1], ("POST", "/api/v2/nodes/launch"))

    def test_wrong_state(self):
        result = self.registry.tools["taks_node_wake"]("49hvbat", True)
        self.assertFalse(result["ok"])
        self.assertEqual(len(self.calls), 1)

    def test_invalid_node_id(self):
        result = self.registry.tools["taks_node_snooze"]("../49hvbat", True)
        self.assertFalse(result["ok"])
        self.assertFalse(self.calls)

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
