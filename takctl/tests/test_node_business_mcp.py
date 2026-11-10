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
                "card_url": "https://example.com/private-card-token"})
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


if __name__ == "__main__":
    unittest.main()
