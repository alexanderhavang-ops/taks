"""Node DevOps tools must stay bounded, read-only and separate from business MCP."""
import unittest
from unittest.mock import patch
from takctl.web.mcp_domains import devops


class NodeDevopsTests(unittest.TestCase):
    def test_tools_are_finite_and_unique(self):
        names = [t["name"] for t in devops.TOOLS]
        self.assertEqual(len(names), len(set(names)))
        for name in ("listening_ports", "service_logs", "service_status",
                     "host_resources", "nginx_check", "cert_status", "installer_tail"):
            self.assertIn(name, names)
        self.assertNotIn("shell_exec", names)

    def test_unknown_service_and_path_rejected(self):
        with self.assertRaises(ValueError):
            devops.call("service_status", {"service": "sshd.service"})
        with self.assertRaises(ValueError):
            devops.call("file_stat", {"path": "/etc/shadow"})
        with self.assertRaises(ValueError):
            devops.call("installer_tail", {"lines": 100000})
        with self.assertRaises(ValueError):
            devops.call("service_logs", {"service": "takserver.service", "lines": True})

    def test_no_extra_arguments(self):
        with self.assertRaises(ValueError):
            devops.call("host_identity", {"command": "id"})
        with self.assertRaises(ValueError):
            devops.call("service_status", {"service": "takserver.service", "extra": "x"})

    def test_read_only_service_status(self):
        with patch.object(devops, "_run", return_value={"exit_code": 0, "stdout": "ActiveState=active"}) as run:
            result = devops.call("service_status", {"service": "takserver.service"})
        self.assertIn("ActiveState=active", result["content"][0]["text"])
        self.assertEqual(run.call_args.args[0][0], "systemctl")
        self.assertNotIn("restart", run.call_args.args[0])

    def test_nginx_test_uses_only_fixed_sudo_command(self):
        with patch.object(devops, "_run", return_value={"exit_code": 0}) as run:
            devops.call("nginx_check", {})
        self.assertEqual(run.call_args.args[0],
                         ["sudo", "-n", "/usr/sbin/nginx", "-t"])

    def test_cert_status_rejects_untrusted_fqdn(self):
        with self.assertRaises(ValueError):
            devops.call("cert_status", {})
        value = devops.call("cert_status", {"fqdn": "../etc/shadow"})
        self.assertIn("Node FQDN unavailable", value["content"][0]["text"])

    def test_expected_ports(self):
        self.assertIn(8446, devops.PORTS)
        self.assertIn(8089, devops.PORTS)
        self.assertIn(8443, devops.PORTS)


if __name__ == "__main__":
    unittest.main()
