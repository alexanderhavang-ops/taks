from __future__ import annotations

from typing import Any, Dict

from martine_server import AgentLoop, RunContext, load_config, resolve_profile
from martine_server.tracing import TraceWriter, new_run_id


def _system_prompt() -> str:
    return (
        'You are Martine, a concise TAKS operational assistant. '
        'Use tools when they materially improve correctness. '
        'Keep final answers brief and concrete. '
        'If a tool result is missing or insufficient, say so plainly.'
    )


def run_once(user_question: str, *, sender_uid: str = '', sender_callsign: str = '') -> Dict[str, Any]:
    cfg = load_config()
    run_id = new_run_id('martine')
    profile = resolve_profile('martine_chat', 'chat.reply')
    trace = TraceWriter(cfg.trace_dir, run_id)
    ctx = RunContext(
        client='martine_chat',
        workload='chat.reply',
        run_id=run_id,
        state_root=cfg.state_dir,
        trace_root=cfg.trace_dir,
        language='sv',
        output_schema='',
        max_turns=int(profile.get('max_turns', cfg.default_max_turns)),
        max_tool_calls=int(profile.get('max_tool_calls', cfg.default_max_tool_calls)),
        allow_repair_turn=bool(profile.get('allow_repair_turn', cfg.default_allow_repair_turn)),
        purpose_prefix='martine',
        sender_uid=sender_uid,
        sender_callsign=sender_callsign,
    )
    loop = AgentLoop(ctx, trace)
    result = loop.run(system_prompt=_system_prompt(), user_input=user_question, final_format='plain text answer')
    out: Dict[str, Any] = {
        'ok': result.ok,
        'run_id': run_id,
        'question': user_question,
        'sender_uid': sender_uid,
        'sender_callsign': sender_callsign,
        'tool_result': result.tool_results[-1]['tool_response'] if result.tool_results else None,
        'final_answer_raw': result.answer_json,
        'answer': result.answer_text,
        'error': result.error or None,
        'turns': result.turns or [],
        'log_files': {
            'dir': str(trace.path),
        },
    }
    trace.write_json('99_result.json', out)
    return out
