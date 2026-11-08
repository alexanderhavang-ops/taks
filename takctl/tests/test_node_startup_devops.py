"""Tests for read-only TAK Server startup observability."""
import unittest
from unittest.mock import patch
from takctl.web.mcp_domains import devops


class StartupDevopsTests(unittest.TestCase):
    def test_tools_discoverable_and_no_shell(self):
        names = {x["name"] for x in devops.TOOLS}
        self.assertTrue({"java_processes", "takserver_logs", "takserver_readiness"} <= names)
        self.assertNotIn("shell_exec", names)

    def test_logs_reject_arbitrary_file(self):
        with patch.object(devops, "_tak_log_files", return_value={"takserver.log": "/opt/tak/logs/takserver.log"}):
            with self.assertRaises(ValueError):
                devops.call("takserver_logs", {"file": "/etc/shadow"})
            with self.assertRaises(ValueError):
                devops.call("takserver_logs", {"file": "../takserver.log"})
            listed = devops.call("takserver_logs", {})
            self.assertIn("takserver.log", listed["content"][0]["text"])

    def test_log_tail_redacts_credentials(self):
        with patch.object(devops, "_tak_log_files", return_value={"takserver.log": "/opt/tak/logs/takserver.log"}), patch.object(devops, "_tail", return_value={"lines": "password=abcd1234\ninitializing\n"}):
            reply = devops.call("takserver_logs", {"file": "takserver.log", "lines": 30})
        self.assertNotIn("abcd1234", reply["content"][0]["text"])
        self.assertIn("[REDACTED]", reply["content"][0]["text"])

    def test_java_cpu_sample_sanitizes_process_args(self):
        with patch.object(devops, "_java_snapshot", side_effect=[{123: (100, 100)}, {123: (140, 101)}]), patch.object(devops.os, "sysconf", side_effect=[100, 4096]), patch("time.sleep"):
            report = devops._java_processes()
        self.assertEqual(report["java_processes"][0]["pid"], 123)
        self.assertGreater(report["java_processes"][0]["cpu_pct_one_core"], 100)
        self.assertNotIn("cmdline", report["java_processes"][0])

    def test_auth_xml_not_exposed(self):
        with patch.object(devops, "_ports", return_value={"ports": []}), patch.object(devops, "_java_processes", return_value={}), patch.object(devops, "_tak_log_files", return_value={}), patch.object(devops.Path, "is_file", return_value=False):
            report = devops._takserver_readiness()
        self.assertEqual(report["auth"]["backend"], "unknown")
        self.assertFalse(report["coreconfig_present"])


if __name__ == "__main__":
    unittest.main()
