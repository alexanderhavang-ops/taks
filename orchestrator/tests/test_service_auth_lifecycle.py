"""Verify scoped MCP authentication exposes the four node lifecycle routes."""
import unittest

from orchestrator_api.service_auth import LIFECYCLE, NODE_DEVOPS_PROBE, NODE_TAKS_PROBE, MARTI_DIAGNOSTICS


class ServiceAuthLifecycleTests(unittest.TestCase):
    def test_new_named_routes_allowed(self):
        for operation in ("pause", "resume", "shutdown"):
            with self.subTest(operation=operation):
                self.assertIsNotNone(
                    LIFECYCLE.fullmatch("/api/v2/nodes/taklabs.aws.tak-hv-sandbox.se/" + operation)
                )

    def test_legacy_routes_remain_allowed(self):
        for operation in ("snooze", "wake", "terminate"):
            self.assertIsNotNone(LIFECYCLE.fullmatch("/api/v2/nodes/taklabs/" + operation))

    def test_devops_probe_path_is_scoped_to_known_node_ids(self):
        self.assertIsNotNone(NODE_DEVOPS_PROBE.fullmatch(
            "/api/v2/nodes/taklabs.aws.tak-hv-sandbox.se/mcp/devops"))
        self.assertIsNone(NODE_DEVOPS_PROBE.fullmatch(
            "/api/v2/nodes/taklabs/mcp/taks"))
        self.assertIsNone(NODE_DEVOPS_PROBE.fullmatch(
            "/api/v2/nodes/../mcp/devops"))

    def test_business_bridge_route_is_scoped(self):
        self.assertIsNotNone(NODE_TAKS_PROBE.fullmatch(
            "/api/v2/nodes/taklabs.aws.tak-hv-sandbox.se/mcp/taks"))
        self.assertIsNone(NODE_TAKS_PROBE.fullmatch(
            "/api/v2/nodes/../mcp/taks"))
        self.assertIsNone(NODE_TAKS_PROBE.fullmatch(
            "/api/v2/nodes/taklabs/mcp/taks/extra"))

    def test_marti_admin_route_is_read_only_and_scoped(self):
        self.assertIsNotNone(MARTI_DIAGNOSTICS.fullmatch(
            "/api/v2/nodes/taklabs.aws.tak-hv-sandbox.se/marti/diagnostics"))
        for path in ("/api/v2/nodes/../marti/diagnostics",
                     "/api/v2/nodes/taklabs/marti/users/delete",
                     "/api/v2/nodes/taklabs/marti/diagnostics/extra"):
            self.assertIsNone(MARTI_DIAGNOSTICS.fullmatch(path))

    def test_unrelated_mutations_not_allowed(self):
        for path in ("/api/v2/nodes/taklabs/delete",
                     "/api/v2/nodes/taklabs/pause/extra",
                     "/api/v2/nodes/../shutdown"):
            self.assertIsNone(LIFECYCLE.fullmatch(path))


if __name__ == "__main__":
    unittest.main()
