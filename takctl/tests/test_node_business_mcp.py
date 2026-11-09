"""Permission and redaction tests for the node TAKCTL Business MCP."""
import json
import unittest
from unittest.mock import patch

from takctl.web.mcp_domains import taks


def text_of(result):
    return json.loads(result["content"][0]["text"])


class NodeBusinessMCPTests(unittest.TestCase):
    def test_discovery_does_not_grant_arbitrary_operation(self):
        names = {t["name"] for t in taks.TOOLS}
        self.assertIn("onboarding_user_create", names)
        self.assertIn("onboarding_send_invite", names)
        self.assertNotIn("shell_exec", names)
        with self.assertRaises(ValueError):
            taks.call("shell_exec", {"command": "id"})
        with self.assertRaises(ValueError):
            taks.call("onboarding_user_create", {
                "username": "alex", "email": "alex@example.com", "admin": True})

    def test_create_requires_explicit_confirmation(self):
        with patch.object(taks, "_request") as http:
            self.assertTrue(text_of(taks.call("onboarding_user_create", {
                "username": "alex", "email": "alex@example.com"
            }))["confirmation_required"])
            http.assert_not_called()

    def test_create_is_non_admin_and_does_not_return_credentials(self):
        def mock_request(method, path, data=None, public_fqdn=None):
            if method == "GET":
                return {"ok": False, "not_found": True}
            self.assertEqual(method, "POST")
            self.assertEqual(data["admin"], False)
            self.assertEqual(data["ctx"]["email"], "alex@example.com")
            self.assertTrue(data["reveal_password"])
            self.assertEqual(data["groups_rw"], ["testers"])
            self.assertEqual(public_fqdn, "taklabs.aws.tak-hv-sandbox.se")
            return {"user": {"username": "alex"}, "taks_identity": {
                "password": "SECRET"}, "card_token": "PRIVATE"}
        with patch.object(taks, "_node_fqdn", return_value="taklabs.aws.tak-hv-sandbox.se"), patch.object(
            taks, "_request", side_effect=mock_request
        ) as http:
            result = text_of(taks.call("onboarding_user_create", {
                "username": "alex", "email": "alex@example.com",
                "group": "testers", "confirm_create": True}))
        self.assertTrue(result["ok"])
        self.assertEqual(http.call_count, 2)
        self.assertNotIn("SECRET", str(result))
        self.assertNotIn("PRIVATE", str(result))

    def test_existing_user_is_not_modified(self):
        with patch.object(taks, "_node_fqdn", return_value="taklabs.aws.tak-hv-sandbox.se"), patch.object(
            taks, "_request", return_value={"user": {"username": "alex"}}
        ) as http:
            result = text_of(taks.call("onboarding_user_create", {
                "username": "alex", "email": "alex@example.com", "confirm_create": True}))
            self.assertFalse(result["ok"])
            self.assertEqual(http.call_count, 1)

    def test_invite_requires_confirmation_and_never_returns_card_link(self):
        with patch.object(taks, "_request") as http:
            result = text_of(taks.call("onboarding_send_invite", {
                "username": "alex", "email": "alex@example.com"}))
            self.assertTrue(result["confirmation_required"])
            http.assert_not_called()
        with patch.object(taks, "_node_fqdn", return_value="taklabs.aws.tak-hv-sandbox.se"), patch.object(
            taks, "_request", return_value={
                "email_status": {"ok": True, "delivery": "resend"},
                "card_url": "https://example.com/private-card-token"}
        ) as http:
            result = text_of(taks.call("onboarding_send_invite", {
                "username": "alex", "email": "alex@example.com",
                "confirm_send": True}))
            self.assertTrue(result["ok"])
            self.assertEqual(result["delivery"], "resend")
            self.assertNotIn("private-card-token", str(result))
            self.assertEqual(http.call_args.args[1], "/api/onboarding/users/alex/email-link")

    def test_bad_usernames_emails_and_arguments_are_rejected(self):
        for username, email in [
            ("../etc", "a@example.com"), ("alex", "not-an-email"),
            ("alex/other", "a@example.com"),
        ]:
            with self.assertRaises(ValueError):
                taks.call("onboarding_user_create", {
                    "username": username, "email": email, "confirm_create": True})
        with self.assertRaises(ValueError):
            taks.call("takctl_health", {"url": "http://somewhere/"})

    def test_api_surface_stays_discovery_only(self):
        schema = {"info": {"title": "TAKCTL"},
                  "paths": {"/api/onboarding/users/{username}/create": {"post": {"summary": "Create"}}}}
        result = taks._surface(schema)
        self.assertEqual(result["paths"]["/api/onboarding/users/{username}/create"], ["POST"])
        with self.assertRaises(ValueError):
            taks._surface(schema, "http://example.com")


class NodeBusinessMCPLoopbackTests(unittest.TestCase):
    """Exercise real loopback HTTP against a single-worker ASGI server."""

    def test_health_and_openapi_can_reenter_server(self):
        import socket
        import threading
        import time
        import urllib.request
        import uvicorn
        from fastapi import FastAPI
        from takctl.web.api import orchestrator_mcp

        app = FastAPI()
        app.include_router(orchestrator_mcp.router)

        @app.get("/api/health")
        async def health():
            return {"ok": True}

        # Use an isolated loopback listener; production port 8080 may be busy.
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        base = "http://127.0.0.1:%s" % sock.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
        thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
        with patch.object(orchestrator_mcp, "require_orchestrator_secret", return_value=None), patch.object(
            taks, "_LOOPBACK", base
        ):
            thread.start()
            try:
                deadline = time.monotonic() + 5
                while not server.started and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertTrue(server.started)
                for tool in ("takctl_health", "api_surface"):
                    request = urllib.request.Request(
                        base + "/api/orchestrator/mcp/taks",
                        data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                         "params": {"name": tool, "arguments": {}}}).encode(),
                        headers={"Content-Type": "application/json"})
                    with urllib.request.urlopen(request, timeout=3) as response:
                        result = text_of(json.load(response)["result"])
                    if tool == "takctl_health":
                        self.assertTrue(result["ok"])
                    else:
                        self.assertIn("/api/health", result["paths"])
            finally:
                server.should_exit = True
                thread.join(timeout=7)
                sock.close()


if __name__ == "__main__":
    unittest.main()
