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

    def test_confirmation_required(self):
        result = self.registry.tools["taks_node_snooze"]("49hvbat")
        self.assertTrue(result["confirmation_required"])
        self.assertFalse(self.calls)

    def test_stop_and_wake(self):
        self.assertTrue(self.registry.tools["taks_node_snooze"]("49hvbat", True)["ok"])
        self.assertEqual(self.calls[-1], ("POST", "/api/v2/nodes/49hvbat/pause"))
        self.state = "stopped"
        self.assertTrue(self.registry.tools["taks_node_wake"]("49hvbat", True)["ok"])

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

if __name__ == "__main__":
    unittest.main()
