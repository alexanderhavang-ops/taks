"""Unit tests for TAKCTL node MCP router contract."""
import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from takctl.node_mcp.endpoint import create_node_mcp_router


class NodeMcpEndpointTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        app = FastAPI()
        app.include_router(create_node_mcp_router(
            verify_orchestrator=lambda request: request.headers.get("authorization") == "Bearer test",
            list_tools=lambda domain: [{"name": "health", "description": domain, "inputSchema": {"type": "object"}}],
            call_tool=lambda domain, name, args: self.calls.append((domain, name, args)) or
                {"content": [{"type": "text", "text": "ok"}]},
        ))
        self.client = TestClient(app)

    def post(self, domain="taks", payload=None, token="Bearer test"):
        if payload is None:
            payload = {"jsonrpc": "2.0", "id": 7, "method": "tools/list"}
        return self.client.post("/api/orchestrator/mcp/" + domain,
                                json=payload, headers={"Authorization": token})

    def test_unauthenticated(self):
        self.assertEqual(self.post(token="").status_code, 401)

    def test_unknown_domain(self):
        self.assertEqual(self.post(domain="unknown").status_code, 404)

    def test_list(self):
        result = self.post().json()
        self.assertEqual(result["id"], 7)
        self.assertEqual(result["result"]["tools"][0]["name"], "health")

    def test_call(self):
        payload = {"jsonrpc": "2.0", "id": 9, "method": "tools/call",
                   "params": {"name": "health", "arguments": {"verbose": True}}}
        self.assertEqual(self.post(payload=payload).status_code, 200)
        self.assertEqual(self.calls, [("taks", "health", {"verbose": True})])

    def test_unsupported_method(self):
        payload = {"jsonrpc": "2.0", "id": 1, "method": "resources/read"}
        self.assertEqual(self.post(payload=payload).status_code, 403)


if __name__ == "__main__":
    unittest.main()
