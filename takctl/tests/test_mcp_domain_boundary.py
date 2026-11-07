"""Ensure node MCP catalogs cannot cross domain boundaries."""
import unittest
from takctl.web.mcp_domains import devops, taks


class DomainBoundaryTests(unittest.TestCase):
    def test_catalogs_disjoint(self):
        d = {tool["name"] for tool in devops.TOOLS}
        t = {tool["name"] for tool in taks.TOOLS}
        self.assertTrue(d)
        self.assertTrue(t)
        self.assertFalse(d & t)

    def test_wrong_domain_rejected(self):
        with self.assertRaises(ValueError):
            devops.call("runtime_status", {})
        with self.assertRaises(ValueError):
            taks.call("host_identity", {})

    def test_unexpected_arguments_rejected(self):
        with self.assertRaises(ValueError):
            taks.call("runtime_status", {"path": "/etc/shadow"})


if __name__ == "__main__":
    unittest.main()
