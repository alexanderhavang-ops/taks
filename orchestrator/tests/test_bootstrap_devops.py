import importlib
from io import BytesIO
import json
from pathlib import Path
import shutil
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch


BUNDLE = Path(__file__).resolve().parents[1] / "orchestrator_core" / "default_bundle"
ENDPOINT = "/api/orchestrator/mcp/devops"


class BootstrapDevOpsTest(unittest.TestCase):
    def test_authenticated_read_only_diagnostics_without_takctl(self):
        with tempfile.TemporaryDirectory() as directory:
            package = Path(directory) / "bootstrap_test"
            shutil.copytree(BUNDLE / "node-devops", package)
            shutil.copyfile(BUNDLE / "install" / "bootstrap-devops.py", package / "server.py")
            with patch.object(sys, "path", [directory, *sys.path]):
                module = importlib.import_module("bootstrap_test.server")

            self.assertEqual(self.rpc(module, "tools/list", token=None)[0], 401)
            self.assertEqual(self.rpc(module, "tools/list", token="invalid")[0], 401)
            status, response = self.rpc(module, "tools/list")
            self.assertEqual(status, 200)
            self.assertIn("installer_tail", {tool["name"] for tool in response["result"]["tools"]})
            with patch.object(module.devops, "_tail", return_value={"lines": "taks/apply,Failed"}) as tail:
                status, response = self.rpc(
                    module, "tools/call", {"name": "installer_tail", "arguments": {"lines": 12}}
                )
            self.assertEqual(status, 200)
            self.assertEqual(response["id"], 42)
            self.assertEqual(json.loads(response["result"]["content"][0]["text"])["lines"], "taks/apply,Failed")
            tail.assert_called_once_with("/var/log/taks-installer-state.log", 12)
            self.assertEqual(self.rpc(module, "tools/call", {"name": "nginx_check"})[0], 400)

    def rpc(self, module, method, params=None, token="test-credential"):
        body = json.dumps({"jsonrpc": "2.0", "id": 42, "method": method, "params": params or {}})
        headers = [
            f"POST {ENDPOINT} HTTP/1.0",
            "Content-Type: application/json",
            f"Content-Length: {len(body)}",
        ]
        if token is not None:
            headers.append(f"Authorization: Bearer {token}")
        incoming = BytesIO("\r\n".join([*headers, "", body]).encode())
        outgoing = BytesIO()
        socket = Mock()
        socket.makefile.return_value = incoming
        socket.sendall.side_effect = outgoing.write
        module.Handler(socket, "", SimpleNamespace(node_secret=b"test-credential"))
        headers, _, response = outgoing.getvalue().partition(b"\r\n\r\n")
        return int(headers.split()[1]), json.loads(response)
