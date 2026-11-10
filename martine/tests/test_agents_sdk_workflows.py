"""Full Agents SDK -> Martine FastMCP tests with no provider/network API calls.

These tests run the real Runner with a ScriptedModel and the actual local
MCP subprocess. They are intentionally independent of OPENAI_API_KEY.
"""
from __future__ import annotations

import asyncio
import json
import os
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
    def setUp(self):
        self.runtime = tempfile.TemporaryDirectory()
        self.addCleanup(self.runtime.cleanup)
        values={}
        for env,name in [('TAKS_RUNTIME_ROOT','takctl'),('MARTINE_RUNTIME_ROOT','martine')]:
            root=Path(self.runtime.name)/name
            (root/'conf.d').mkdir(parents=True)
            (root/'conf.d/test.conf').write_text('fqdn = test.invalid\nmartine_state_dir = '+self.runtime.name+'/state\n')
            values[env]=str(root)
        values['MARTINE_CHAT_DB']=str(Path(self.runtime.name)/'chat.sqlite3')
        patcher=patch.dict(os.environ,values)
        patcher.start();self.addCleanup(patcher.stop)

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

    def test_real_mcp_server_rejects_cross_user_and_raw_log_calls(self):
        from agents.mcp import MCPServerStdio
        from martine.mcp_server.client import _build_child_env
        import sys
        actor={'username':'alice','unit':'one','authenticated':True,'admin':False}
        async def exercise():
            env={**_build_child_env(),'MARTINE_AUTH_CONTEXT':json.dumps(actor)}
            async with MCPServerStdio(name='scope-test',params={'command':sys.executable,'args':['-m','martine.main','mcp-stdio'],'env':env}) as server:
                for name,args in [('get_onboarding_diagnostics',{'username':'bob'}),('read_diagnostic_log',{'source':'installer'})]:
                    result=await server.call_tool(name,args)
                    self.assertTrue(result.isError, name)
        asyncio.run(exercise())

    def test_real_mcp_mutation_only_creates_pending_human_approval(self):
        from agents.mcp import MCPServerStdio
        from martine.mcp_server.client import _build_child_env
        import sys, sqlite3
        actor={'username':'admin','unit':'one','authenticated':True,'admin':True}
        async def exercise():
            env={**_build_child_env(),'MARTINE_AUTH_CONTEXT':json.dumps(actor)}
            async with MCPServerStdio(name='approval-test',params={'command':sys.executable,'args':['-m','martine.main','mcp-stdio'],'env':env}) as server:
                result=await server.call_tool('request_business_change',{'service':'mumble','operation':'channel_create','arguments':{'name':'test','parent':0}})
                self.assertFalse(result.isError)
        asyncio.run(exercise())
        with sqlite3.connect(os.environ['MARTINE_CHAT_DB']) as db:
            self.assertEqual(db.execute('SELECT status FROM actions').fetchall(),[('pending',)])

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

    def test_session_continuity_and_sender_isolation(self):
        from agents.testing import ScriptedModel, assistant_message
        first_model = ScriptedModel([[assistant_message("Bravo is north.")]])
        second_model = ScriptedModel([[assistant_message("I remember Bravo.")]])
        other_model = ScriptedModel([[assistant_message("New user.")]])
        clients = [AsyncMock(), AsyncMock(), AsyncMock()]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            instances = [(first_model, "openai", clients[0]),
                         (second_model, "openai", clients[1]),
                         (other_model, "openai", clients[2])]
            with patch(
                "martine_server.agent_loop._runtime_model",
                side_effect=instances,
            ):
                for idx, (uid, question) in enumerate((
                    ("ANDROID-ALEX", "Where is Bravo?"),
                    ("ANDROID-ALEX", "What did I ask?"),
                    ("ANDROID-BOB", "Hello"),
                )):
                    ctx = make_ctx(root, uid=uid)
                    run = AgentLoop(ctx, TraceWriter(ctx.trace_root, f"run-{idx}")).run(
                        system_prompt="You are Martine.",
                        user_input=question,
                    )
                    self.assertTrue(run.ok, run.error)
        first_model.assert_complete()
        second_model.assert_complete()
        other_model.assert_complete()
        historical = json.dumps(second_model.first_call.input, ensure_ascii=False)
        isolated = json.dumps(other_model.first_call.input, ensure_ascii=False)
        self.assertIn("Where is Bravo?", historical)
        self.assertNotIn("Where is Bravo?", isolated)

    def test_llm3_structured_report_contract(self):
        from agents.testing import assistant_message
        result = self._run(
            [[assistant_message('{"html":"<p>Operational summary</p>"}')]],
            final_format="JSON object with html field",
        )
        self.assertEqual(result.answer_json["html"], "<p>Operational summary</p>")


if __name__ == "__main__":
    unittest.main()
