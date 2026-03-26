from __future__ import annotations

import json
from typing import Any, Dict, List

from martine.llm.bedrock_adapter import MartineLlm
from martine.mcp_server.client import call_tool_via_mcp, list_tools_via_mcp
from martine.state.runlog import new_run_id, write_json, write_text


def _build_tool_selection_prompt(user_question: str, tools: List[Dict[str, Any]]) -> str:
    tools_json = json.dumps(tools, ensure_ascii=False, indent=2)
    return f"""You are Martine, a TAKS operational assistant.

You must decide whether ONE available tool should be used before answering.

Return JSON only.
First non-whitespace character must be {{
Last non-whitespace character must be }}

Allowed response schema:
{{
  "use_tool": true or false,
  "tool_name": "<tool name or empty string>",
  "tool_args": {{...}},
  "reason": "<very short reason>"
}}

Rules:
- Use at most one tool.
- Only choose a tool from the AVAILABLE_TOOLS list.
- If no tool is needed, set use_tool=false and tool_name="" and tool_args={{}}.
- Do not answer the user's question yet.
- Do not include markdown fences.

AVAILABLE_TOOLS:
{tools_json}

USER_QUESTION:
{user_question}
"""


def _build_final_answer_prompt(
    user_question: str,
    tool_result: Dict[str, Any] | None,
) -> str:
    tool_json = json.dumps(tool_result, ensure_ascii=False, indent=2) if tool_result is not None else "null"
    return f"""You are Martine, a concise TAKS operational assistant.

Answer the user's question briefly and concretely.
Prefer 2-6 sentences.
If a tool result is provided, use only facts from it.
If the tool result is missing or insufficient, say so plainly.
Do not mention hidden reasoning.
Do not output JSON.
Do not use markdown fences.

USER_QUESTION:
{user_question}

TOOL_RESULT:
{tool_json}
"""


def run_once(user_question: str) -> Dict[str, Any]:
    run_id = new_run_id()
    llm = MartineLlm()
    tools = list_tools_via_mcp()
    tool_names = [str(t.get("name") or "") for t in tools]

    select_prompt = _build_tool_selection_prompt(user_question, tools)
    write_text(run_id, "01_tool_selection_prompt.txt", select_prompt)

    select_resp = llm.complete_text(
        prompt=select_prompt,
        temperature=0.0,
        max_tokens=300,
    )
    write_json(run_id, "02_tool_selection_llm.json", select_resp)

    out: Dict[str, Any] = {
        "ok": False,
        "run_id": run_id,
        "question": user_question,
        "tool_selection_raw": select_resp,
        "tool_result": None,
        "final_answer_raw": None,
        "answer": "",
        "error": None,
        "log_files": {},
    }

    if not select_resp.get("ok"):
        out["error"] = f"tool selection failed: {select_resp.get('error')}"
        return out

    text = str(select_resp.get("text") or "").strip()
    try:
        selection = json.loads(text)
    except Exception as e:
        out["error"] = f"tool selection was not valid JSON: {e}; raw={text[:800]}"
        return out

    write_json(run_id, "03_tool_selection_parsed.json", selection)

    use_tool = bool(selection.get("use_tool"))
    tool_name = str(selection.get("tool_name") or "").strip()
    tool_args = selection.get("tool_args") or {}

    tool_result: Dict[str, Any] | None = None

    if use_tool:
        if tool_name not in tool_names:
            out["error"] = f"model chose unknown tool: {tool_name}"
            out["selection"] = selection
            return out
        if not isinstance(tool_args, dict):
            out["error"] = f"tool_args must be an object/dict, got: {type(tool_args).__name__}"
            out["selection"] = selection
            return out

        tool_resp = call_tool_via_mcp(tool_name, tool_args)
        write_json(run_id, "04_tool_call_raw.json", tool_resp)
        tool_result = tool_resp.get("structured")
        if tool_result is None:
            tool_result = tool_resp
        write_json(run_id, "05_tool_result.json", tool_result)

    final_prompt = _build_final_answer_prompt(user_question, tool_result)
    write_text(run_id, "06_final_answer_prompt.txt", final_prompt)

    final_resp = llm.complete_text(
        prompt=final_prompt,
        temperature=0.2,
        max_tokens=400,
    )
    write_json(run_id, "07_final_answer_llm.json", final_resp)

    out["selection"] = selection
    out["tool_result"] = tool_result
    out["final_answer_raw"] = final_resp

    if not final_resp.get("ok"):
        out["error"] = f"final answer failed: {final_resp.get('error')}"
        return out

    out["ok"] = True
    out["answer"] = str(final_resp.get("text") or "").strip()
    write_text(run_id, "08_final_answer.txt", out["answer"])

    out["log_files"] = {
        "dir": f"/opt/tak/tools/martine/state/logs/{run_id}",
        "tool_selection_prompt": f"/opt/tak/tools/martine/state/logs/{run_id}/01_tool_selection_prompt.txt",
        "tool_selection_llm": f"/opt/tak/tools/martine/state/logs/{run_id}/02_tool_selection_llm.json",
        "tool_selection_parsed": f"/opt/tak/tools/martine/state/logs/{run_id}/03_tool_selection_parsed.json",
        "tool_call_raw": f"/opt/tak/tools/martine/state/logs/{run_id}/04_tool_call_raw.json",
        "tool_result": f"/opt/tak/tools/martine/state/logs/{run_id}/05_tool_result.json",
        "final_answer_prompt": f"/opt/tak/tools/martine/state/logs/{run_id}/06_final_answer_prompt.txt",
        "final_answer_llm": f"/opt/tak/tools/martine/state/logs/{run_id}/07_final_answer_llm.json",
        "final_answer": f"/opt/tak/tools/martine/state/logs/{run_id}/08_final_answer.txt",
    }
    write_json(run_id, "09_result.json", out)
    return out
