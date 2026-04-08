from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from martine.llm.bedrock_adapter import MartineLlm
from martine.logging import get_logger, setup_martine_logging

from .output_validation import parse_structured_json
from .tool_client import call_tool, list_tools
from .tracing import TraceWriter
from .run_context import RunContext


log = get_logger(__name__)

@dataclass
class AgentLoopResult:
    ok: bool
    answer_text: str = ""
    answer_json: dict[str, Any] | None = None
    tool_results: list[dict[str, Any]] | None = None
    turns: list[dict[str, Any]] | None = None
    error: str = ""


class AgentLoop:
    def __init__(self, ctx: RunContext, trace: TraceWriter):
        self.ctx = ctx
        self.trace = trace
        self.llm = MartineLlm()

    def _preview(self, value: Any, limit: int = 1200) -> Any:
        try:
            s = json.dumps(value, ensure_ascii=False, sort_keys=True)
        except Exception:
            s = str(value)
        if len(s) <= limit:
            return value
        return {"truncated": True, "preview": s[:limit]}

    def _extract_reference_doc_names(self, raw: Any) -> list[str]:
        names: list[str] = []

        def add_name(v: Any) -> None:
            s = str(v or "").strip()
            if s and s not in names:
                names.append(s)

        if isinstance(raw, dict):
            items = raw.get("items")
            if isinstance(items, list):
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    add_name(item.get("title"))
                    add_name(item.get("name"))
                    add_name(item.get("doc_title"))
                    add_name(item.get("doc_name"))
                    add_name(item.get("doc_id"))
            else:
                for k in ("title", "name", "doc_title", "doc_name", "doc_id"):
                    add_name(raw.get(k))

        elif isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict):
                    add_name(item.get("title"))
                    add_name(item.get("name"))
                    add_name(item.get("doc_title"))
                    add_name(item.get("doc_name"))
                    add_name(item.get("doc_id"))
                else:
                    add_name(item)

        return names

    def _list_reference_docs_once(self, tool_names: set[str]) -> dict[str, Any]:
        if "list_reference_docs" not in tool_names:
            out = {
                "ok": False,
                "available": False,
                "tool_name": "list_reference_docs",
                "names": [],
                "raw": None,
            }
            self.trace.append_event("reference_docs_skipped", out)
            return out

        try:
            self.trace.append_event("tool_call_started", {
                "turn": 0,
                "tool_name": "list_reference_docs",
                "tool_args": {"only_active": True},
                "reason": "discover available reference document names",
            })
            tool_resp = call_tool("list_reference_docs", {"only_active": True})
        except Exception as e:
            out = {
                "ok": False,
                "available": True,
                "tool_name": "list_reference_docs",
                "error": f"{type(e).__name__}: {e}",
                "names": [],
                "raw": None,
            }
            self.trace.write_json("00_reference_docs.json", out)
            self.trace.append_event("tool_call_finished", {
                "turn": 0,
                "tool_name": "list_reference_docs",
                "ok": False,
                "error": out["error"],
            })
            return out

        structured = tool_resp.get("structured", tool_resp) if isinstance(tool_resp, dict) else tool_resp
        names = self._extract_reference_doc_names(structured)

        out = {
            "ok": True,
            "available": True,
            "tool_name": "list_reference_docs",
            "names": names,
            "raw": structured,
        }
        self.trace.write_json("00_reference_docs.json", out)
        self.trace.append_event("tool_call_finished", {
            "turn": 0,
            "tool_name": "list_reference_docs",
            "ok": True,
            "result_preview": self._preview({"names": names[:50]}),
        })
        return out

    def _prompt(
        self,
        *,
        system_prompt: str,
        user_input: str,
        tools: list[dict[str, Any]],
        turns: list[dict[str, Any]],
        final_format: str,
        reference_doc_names: list[str],
    ) -> str:
        tools_json = json.dumps(tools, ensure_ascii=False, indent=2)
        turns_json = json.dumps(turns, ensure_ascii=False, indent=2)
        run_ctx = {
            "client": self.ctx.client,
            "workload": self.ctx.workload,
            "language": self.ctx.language,
            "output_schema": self.ctx.output_schema,
            "sender_uid": self.ctx.sender_uid,
            "sender_callsign": self.ctx.sender_callsign,
            "extras": self.ctx.extras,
        }

        docs_block = "REFERENCE_DOCUMENT_NAMES:\n[]\n\n"
        if reference_doc_names:
            docs_block = (
                "REFERENCE_DOCUMENT_NAMES:\n"
                + json.dumps(reference_doc_names[:200], ensure_ascii=False, indent=2)
                + "\n\n"
                + "Use these names as a hint for what doctrine/reference material exists behind the document tools.\n"
                + "Do not assume any document content unless you actually call a document tool.\n"
                + "If the user asks what a handbook/manual/doctrine says, strongly prefer the reference document tools first.\n\n"
            )

        return (
            f"{system_prompt.strip()}\n\n"
            "You are running inside the Martine Server agent loop.\n"
            "You may either call one tool, or return the final answer.\n"
            "Return JSON only.\n"
            "Schema:\n"
            "{\n"
            '  "action": "tool" or "final",\n'
            '  "reason": "short reason",\n'
            '  "tool_name": "<tool name or empty>",\n'
            '  "tool_args": { ... },\n'
            '  "final_text": "<final text answer when action=final>",\n'
            '  "final_json": { ... structured final output when action=final and schema requires JSON }\n'
            "}\n\n"
            "Rules:\n"
            "- Use at most one tool per turn.\n"
            "- If you already have enough information, return action=final.\n"
            "- Do not emit markdown fences.\n"
            "- For doctrine, handbook, chapter, and reference-material questions, prefer the reference document tools before answering.\n"
            "- Prefer search_reference_docs_semantic for broad conceptual questions about what a handbook says.\n"
            "- Prefer search_reference_docs for exact phrases, exact identifiers, or when the user clearly names a specific section title.\n"
            "- After finding a promising document hit, use get_reference_doc_context or get_reference_section on a later turn when needed.\n"
            f"- Desired final format: {final_format}.\n"
            "- Max remaining turns are limited; be efficient.\n\n"
            f"AVAILABLE_TOOLS:\n{tools_json}\n\n"
            + docs_block
            + f"RUN_CONTEXT:\n{json.dumps(run_ctx, ensure_ascii=False, indent=2)}\n\n"
            + f"TURN_HISTORY:\n{turns_json}\n\n"
            + f"USER_INPUT:\n{user_input.strip()}\n"
        )

    def run(self, *, system_prompt: str, user_input: str, final_format: str = "text") -> AgentLoopResult:
        setup_martine_logging()
        log.info('agent_loop_start run_id=%s sender_callsign=%s sender_uid=%s user_input=%r', self.ctx.run_id, self.ctx.sender_callsign, self.ctx.sender_uid, user_input[:500])
        tools = list_tools()
        tool_names = {str(t.get("name") or "") for t in tools}
        self.trace.append_event("run_started", {
            "client": self.ctx.client,
            "workload": self.ctx.workload,
            "language": self.ctx.language,
            "max_turns": self.ctx.max_turns,
            "max_tool_calls": self.ctx.max_tool_calls,
            "user_input": user_input,
        })

        ref_docs = self._list_reference_docs_once(tool_names)
        reference_doc_names = list(ref_docs.get("names") or [])

        turns: list[dict[str, Any]] = []
        tool_results: list[dict[str, Any]] = []
        tool_calls = 0

        for turn_idx in range(1, max(1, self.ctx.max_turns) + 1):
            self.trace.append_event("turn_started", {
                "turn": turn_idx,
                "tool_calls_used": tool_calls,
            })
            prompt = self._prompt(
                system_prompt=system_prompt,
                user_input=user_input,
                tools=tools,
                turns=turns,
                final_format=final_format,
                reference_doc_names=reference_doc_names,
            )
            self.trace.write_text(f"{turn_idx:02d}_prompt.txt", prompt)
            log.info('agent_loop_turn_llm turn=%s tool_calls_used=%s', turn_idx, tool_calls)
            resp = self.llm.complete_text(
                prompt=prompt,
                temperature=0.1,
                max_tokens=int(self.ctx.max_output_tokens),
                purpose=f"{self.ctx.purpose_prefix}:agent_loop",
            )
            self.trace.write_json(f"{turn_idx:02d}_llm.json", resp)
            if not resp.get("ok"):
                err = f"llm_failed:{resp.get('error')}"
                self.trace.append_event("run_failed", {
                    "turn": turn_idx,
                    "error": err,
                })
                return AgentLoopResult(ok=False, error=err, turns=turns, tool_results=tool_results)

            text = str(resp.get("text") or "").strip()
            log.info('agent_loop_llm_done turn=%s ok=%s text_preview=%r', turn_idx, resp.get('ok'), text[:500])
            try:
                obj = parse_structured_json(text)
            except Exception as e:
                log.exception('agent_loop_tool_failed turn=%s tool_name=%s error=%s', turn_idx, tool_name, e)
                err = f"{type(e).__name__}: {e}"
                turns.append({
                    "turn": turn_idx,
                    "kind": "llm_parse_error",
                    "raw_text": text[:4000],
                    "error": err,
                })
                self.trace.append_event("llm_parse_error", {
                    "turn": turn_idx,
                    "error": err,
                    "raw_text_preview": text[:1200],
                })
                if self.ctx.allow_repair_turn and turn_idx < self.ctx.max_turns:
                    turns.append({
                        "turn": turn_idx,
                        "kind": "system_feedback",
                        "message": "Previous output was invalid JSON. Return valid JSON with the required schema.",
                    })
                    self.trace.append_event("repair_turn_requested", {
                        "turn": turn_idx,
                        "message": "Previous output was invalid JSON. Return valid JSON with the required schema.",
                    })
                    continue
                self.trace.append_event("run_failed", {
                    "turn": turn_idx,
                    "error": f"parse_failed:{err}",
                })
                return AgentLoopResult(ok=False, error=f"parse_failed:{err}", turns=turns, tool_results=tool_results)

            self.trace.write_json(f"{turn_idx:02d}_parsed.json", obj)
            action = str(obj.get("action") or "").strip().lower()
            reason = str(obj.get("reason") or "").strip()

            self.trace.append_event("llm_response_parsed", {
                "turn": turn_idx,
                "action": action,
                "reason": reason,
                "tool_name": str(obj.get("tool_name") or "").strip(),
            })

            if action == "final":
                log.info('agent_loop_final turn=%s reason=%r', turn_idx, reason)
                final_text = str(obj.get("final_text") or "").strip()
                final_json = obj.get("final_json") if isinstance(obj.get("final_json"), dict) else None
                self.trace.append_event("final_answer", {
                    "turn": turn_idx,
                    "reason": reason,
                    "answer_preview": final_text[:1200],
                    "has_final_json": final_json is not None,
                })
                self.trace.append_event("run_finished", {
                    "ok": True,
                    "turn": turn_idx,
                })
                return AgentLoopResult(
                    ok=True,
                    answer_text=final_text,
                    answer_json=final_json,
                    turns=turns + [{"turn": turn_idx, "kind": "final", "reason": reason}],
                    tool_results=tool_results,
                )

            if action != "tool":
                turns.append({"turn": turn_idx, "kind": "invalid_action", "payload": obj})
                self.trace.append_event("invalid_action", {
                    "turn": turn_idx,
                    "payload": self._preview(obj),
                })
                if self.ctx.allow_repair_turn and turn_idx < self.ctx.max_turns:
                    turns.append({
                        "turn": turn_idx,
                        "kind": "system_feedback",
                        "message": "action must be tool or final.",
                    })
                    self.trace.append_event("repair_turn_requested", {
                        "turn": turn_idx,
                        "message": "action must be tool or final.",
                    })
                    continue
                self.trace.append_event("run_failed", {
                    "turn": turn_idx,
                    "error": "invalid_action",
                })
                return AgentLoopResult(ok=False, error="invalid_action", turns=turns, tool_results=tool_results)

            if tool_calls >= self.ctx.max_tool_calls:
                self.trace.append_event("run_failed", {
                    "turn": turn_idx,
                    "error": "max_tool_calls_exceeded",
                })
                return AgentLoopResult(ok=False, error="max_tool_calls_exceeded", turns=turns, tool_results=tool_results)

            tool_name = str(obj.get("tool_name") or "").strip()
            log.info('agent_loop_tool_selected turn=%s tool_name=%s reason=%r tool_args=%s', turn_idx, tool_name, reason, obj.get('tool_args'))
            tool_args = obj.get("tool_args") or {}
            if tool_name not in tool_names:
                turns.append({"turn": turn_idx, "kind": "invalid_tool", "tool_name": tool_name})
                self.trace.append_event("invalid_tool", {
                    "turn": turn_idx,
                    "tool_name": tool_name,
                })
                if self.ctx.allow_repair_turn and turn_idx < self.ctx.max_turns:
                    turns.append({
                        "turn": turn_idx,
                        "kind": "system_feedback",
                        "message": f"Unknown tool: {tool_name}",
                    })
                    self.trace.append_event("repair_turn_requested", {
                        "turn": turn_idx,
                        "message": f"Unknown tool: {tool_name}",
                    })
                    continue
                self.trace.append_event("run_failed", {
                    "turn": turn_idx,
                    "error": f"unknown_tool:{tool_name}",
                })
                return AgentLoopResult(ok=False, error=f"unknown_tool:{tool_name}", turns=turns, tool_results=tool_results)

            if not isinstance(tool_args, dict):
                self.trace.append_event("run_failed", {
                    "turn": turn_idx,
                    "error": "tool_args_not_object",
                })
                return AgentLoopResult(ok=False, error="tool_args_not_object", turns=turns, tool_results=tool_results)

            if tool_name in {
                "get_my_position",
                "get_my_mgrs",
                "get_distance_to_callsign",
                "get_nearest_friendly",
                "get_enemy_contacts_near_me",
            }:
                tool_args.setdefault("sender_uid", self.ctx.sender_uid)
                tool_args.setdefault("sender_callsign", self.ctx.sender_callsign)
            if tool_name in {"get_contact_status", "get_last_seen"}:
                tool_args.setdefault("sender_callsign", self.ctx.sender_callsign)

            self.trace.append_event("tool_call_started", {
                "turn": turn_idx,
                "tool_name": tool_name,
                "reason": reason,
                "tool_args": self._preview(tool_args),
            })
            try:
                tool_resp = call_tool(tool_name, tool_args)
                log.info('agent_loop_tool_finished turn=%s tool_name=%s tool_response_preview=%r', turn_idx, tool_name, str(tool_resp)[:1000])
            except Exception as e:
                err = f"{type(e).__name__}: {e}"
                self.trace.append_event("tool_call_finished", {
                    "turn": turn_idx,
                    "tool_name": tool_name,
                    "ok": False,
                    "error": err,
                })
                self.trace.append_event("run_failed", {
                    "turn": turn_idx,
                    "error": f"tool_failed:{tool_name}:{err}",
                })
                return AgentLoopResult(
                    ok=False,
                    error=f"tool_failed:{tool_name}:{err}",
                    turns=turns,
                    tool_results=tool_results,
                )

            tool_calls += 1
            tool_results.append({
                "tool_name": tool_name,
                "tool_args": tool_args,
                "tool_response": tool_resp,
            })
            self.trace.write_json(f"{turn_idx:02d}_tool.json", tool_results[-1])
            self.trace.append_event("tool_call_finished", {
                "turn": turn_idx,
                "tool_name": tool_name,
                "ok": True,
                "result_preview": self._preview(tool_resp.get("structured", tool_resp) if isinstance(tool_resp, dict) else tool_resp),
            })
            turns.append({
                "turn": turn_idx,
                "kind": "tool",
                "tool_name": tool_name,
                "reason": reason,
                "tool_args": tool_args,
                "tool_result": tool_resp.get("structured", tool_resp),
            })

        self.trace.append_event("run_failed", {
            "error": "max_turns_exceeded",
        })
        return AgentLoopResult(ok=False, error="max_turns_exceeded", turns=turns, tool_results=tool_results)
