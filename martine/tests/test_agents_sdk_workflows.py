"""Full Agents SDK -> Martine FastMCP tests with no provider/network API calls.

These tests run the real Runner with a ScriptedModel and the actual local
MCP subprocess. They are intentionally independent of OPENAI_API_KEY.
"""
from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from martine_server.agent_loop import AgentLoop
from martine_server.run_context import RunContext
from martine_server.tracing import TraceWriter


def make_ctx(root: Path, *, uid: str = "") -> RunContext:
    return RunContext(
        client="martine_chat", workload="chat.reply", run_id="scripted-test",
        state_root=str(root), trace_root=str(root / "logs"),
        sender_uid=uid, sender_callsign="TestOperator",
        max_turns=5, max_tool_calls=5,
    )


class RealAgentsSdkUseCases(unittest.TestCase):
    def _run(self, steps, *, final_format="plain text answer"):
        from agents.testing import ScriptedModel
        model = ScriptedModel(steps)
        client = AsyncMock()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            ctx = make_ctx(root)
            with patch(
                "martine_server.agent_loop._runtime_model",
                return_value=(model, "openai", client),
            ):
                result = AgentLoop(
                    ctx, TraceWriter(ctx.trace_root, "scripted-test"),
                ).run(
                    system_prompt="You are Martine, the TAK operations assistant.",
                    user_input="Test request",
                    final_format=final_format,
                )
        self.assertTrue(result.ok, result.error)
        model.assert_complete()
        self.assertGreaterEqual(len(model.calls), 1)
        return result

    def test_plain_geochat_reply_with_real_runner(self):
        from agents.testing import assistant_message
        result = self._run([[assistant_message("Hej! Jag är Martine.")]])
        self.assertIn("Martine", result.answer_text)

    def test_time_mcp_tool_roundtrip(self):
        from agents.testing import assistant_message, function_call
        result = self._run([
            [function_call("get_current_time", {}, call_id="time-1")],
            [assistant_message("Current time retrieved.")],
        ])
        self.assertEqual(result.answer_text, "Current time retrieved.")
        self.assertTrue(result.tool_results)

    def test_document_rag_search_through_mcp(self):
        from agents.testing import assistant_message, function_call
        result = self._run([
            [function_call("list_reference_docs", {"only_active": True}, call_id="docs-1")],
            [assistant_message("I checked the uploaded manuals.")],
        ])
        self.assertTrue(result.tool_results)
        self.assertIn("uploaded manuals", result.answer_text)

    def test_llm3_structured_report_contract(self):
        from agents.testing import assistant_message
        result = self._run(
            [[assistant_message('{"html":"<p>Operational summary</p>"}')]],
            final_format="JSON object with html field",
        )
        self.assertEqual(result.answer_json["html"], "<p>Operational summary</p>")


if __name__ == "__main__":
    unittest.main()
