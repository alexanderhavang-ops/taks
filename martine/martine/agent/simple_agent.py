from __future__ import annotations

from typing import Any, Dict

from martine_server import AgentLoop, RunContext, load_config, resolve_profile
from martine_server.tracing import TraceWriter, new_run_id
from martine.logging import get_logger, setup_martine_logging


log = get_logger(__name__)

def _system_prompt() -> str:
    return (
        'You are Martine, a concise TAKS operational assistant. '
        'Use tools when they materially improve correctness. '
        'For doctrine, handbook, chapter, and reference-document questions, prefer the reference document tools before answering. '
        'Prefer semantic reference-doc search for broad conceptual questions, and exact/keyword search for exact names or phrases. '
        'If a user asks to be onboarded for voice, Vx, or Mumble, use the send_voice_onboarding tool rather than only describing the steps. '
        'If a user asks to send or install ATAK plugins, use the send_plugin_onboarding tool. Default to package_id "plugins-basic" unless the user clearly asks for another registered package. '
        'Plugin and voice onboarding are on-demand tools. Do not send onboarding packages proactively to new users unless explicitly asked. '
        'When send_plugin_onboarding returns user_message_sv/user_message_en or user_guidance_sv/user_guidance_en, reuse that wording in the final answer instead of inventing new install instructions. Prefer Swedish when the user writes in Swedish, otherwise English. '
        'Keep final answers brief and concrete. '
        'If a tool result is missing or insufficient, say so plainly.'
    )


def run_once(user_question: str, *, sender_uid: str = '', sender_callsign: str = '') -> Dict[str, Any]:
    setup_martine_logging()
    log.info('run_once_start sender_callsign=%s sender_uid=%s question=%r', sender_callsign, sender_uid, user_question[:500])
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
        max_output_tokens=int(profile.get('max_output_tokens', cfg.default_max_output_tokens)),
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
    log.info('run_once_done ok=%s run_id=%s error=%s answer_preview=%r log_dir=%s', out.get('ok'), run_id, out.get('error'), str(out.get('answer') or '')[:500], str(trace.path))
    return out
