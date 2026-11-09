"""Live Martine inference integration tests (explicitly opt-in; paid API calls).

Run on an installed TAK node with real Martine configuration and API key.
No credentials or full model outputs are logged. No ATAK messages are sent.
"""
from __future__ import annotations

import json
import os
import unittest
from pathlib import Path

from martine.agent.simple_agent import run_once
from martine_server.agent_loop import _read_private_key


@unittest.skipUnless(os.environ.get("MARTINE_LIVE_TESTS") == "1", "live inference requires explicit opt-in")
class LiveInference(unittest.TestCase):
    def test_real_openai_response(self):
        self.assertTrue(_read_private_key(), "Missing OpenAI key in node's Martine secrets")
        result = run_once(
            "Reply with the single exact token MARTINE_LIVE_OK. No other words.",
            sender_uid="MARTINE-LIVE-TEST",
            sender_callsign="MartineTest",
        )
        self.assertTrue(result.get("ok"), str(result.get("error"))[:250])
        self.assertIn("MARTINE_LIVE_OK", str(result.get("answer", "")))

    def test_real_mcp_tool_selection(self):
        self.assertTrue(_read_private_key(), "Missing OpenAI key in node's Martine secrets")
        result = run_once(
            "Use the get_current_time MCP tool, then answer with the current UTC year as four digits.",
            sender_uid="MARTINE-LIVE-TEST",
            sender_callsign="MartineTest",
        )
        self.assertTrue(result.get("ok"), str(result.get("error"))[:250])
        self.assertTrue(result.get("tool_result"), "Model did not call a Martine MCP tool")
        self.assertIn("2026", str(result.get("answer", "")))


if __name__ == "__main__":
    unittest.main()
