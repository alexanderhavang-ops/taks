"""Offline regression tests for Martine's Agents SDK compatibility facade."""
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from martine_server.agent_loop import AgentLoop, _chat_session, _instructions, _read_private_key
from martine_server.run_context import RunContext
from martine_server.tracing import TraceWriter


def context(root, client="martine_chat", uid="ANDROID-ALEX"):
    return RunContext(
        client=client, workload="chat.reply", run_id="test",
        state_root=str(root), trace_root=str(root / "logs"),
        sender_uid=uid, sender_callsign="Alex",
    )


class AgentMigrationTests(unittest.TestCase):
    def test_context_and_rag_instructions(self):
        with tempfile.TemporaryDirectory() as d:
            txt = _instructions("You are Martine", context(Path(d)), "plain text answer")
        self.assertIn("ANDROID-ALEX", txt)
        self.assertIn("reference-document tools", txt)
        self.assertIn("Never invent another sender identity", txt)

    def test_chat_session_not_used_by_llm3(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(_chat_session(context(Path(d), client="llm3", uid="")))
            self.assertFalse((Path(d) / "sessions").exists())

    def test_session_identity_is_stable_and_not_plain_uid(self):
        class FakeSession:
            def __init__(self, sid, path):
                self.sid, self.path = sid, path
        with tempfile.TemporaryDirectory() as d:
            with patch.dict("sys.modules", {"agents": SimpleNamespace(SQLiteSession=FakeSession)}):
                first = _chat_session(context(Path(d)))
                second = _chat_session(context(Path(d)))
                third = _chat_session(context(Path(d), uid="ANDROID-OTHER"))
            self.assertEqual(first.sid, second.sid)
            self.assertNotEqual(first.sid, third.sid)
            self.assertNotIn("ANDROID-ALEX", first.sid)
            self.assertTrue(Path(first.path).parent.is_dir())

    def test_key_from_environment(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-only"}, clear=False):
            self.assertEqual(_read_private_key(), "test-only")

    def test_plain_text_result(self):
        async def fake_agent(ctx, system, question, fmt):
            return SimpleNamespace(final_output="Hej Alex", new_items=[]), "openai"
        with tempfile.TemporaryDirectory() as d:
            ctx = context(Path(d))
            with patch("martine_server.agent_loop._run_agent", side_effect=fake_agent):
                result = AgentLoop(ctx, TraceWriter(ctx.trace_root, "run")).run(
                    system_prompt="Martine", user_input="Hej")
            self.assertTrue(result.ok)
            self.assertEqual(result.answer_text, "Hej Alex")

    def test_llm3_requires_json_object(self):
        async def fake_agent(ctx, system, question, fmt):
            return SimpleNamespace(final_output='{"html":"<p>ok</p>"}', new_items=[]), "openai"
        with tempfile.TemporaryDirectory() as d:
            ctx = context(Path(d), client="llm3", uid="")
            with patch("martine_server.agent_loop._run_agent", side_effect=fake_agent):
                result = AgentLoop(ctx, TraceWriter(ctx.trace_root, "run")).run(
                    system_prompt="LLM3", user_input="Report", final_format="JSON object with html field")
            self.assertTrue(result.ok)
            self.assertEqual(result.answer_json["html"], "<p>ok</p>")

    def test_invalid_llm3_json_is_not_marked_successful(self):
        async def fake_agent(ctx, system, question, fmt):
            return SimpleNamespace(final_output="not json", new_items=[]), "openai"
        with tempfile.TemporaryDirectory() as d:
            ctx = context(Path(d), client="llm3", uid="")
            with patch("martine_server.agent_loop._run_agent", side_effect=fake_agent):
                result = AgentLoop(ctx, TraceWriter(ctx.trace_root, "run")).run(
                    system_prompt="LLM3", user_input="Report", final_format="JSON object")
            self.assertFalse(result.ok)
            self.assertIn("Invalid structured result", result.error)


if __name__ == "__main__":
    unittest.main()
