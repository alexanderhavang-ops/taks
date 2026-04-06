from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

REPO_ROOT = SCRIPT_ROOT.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

TAKS_ROOT = REPO_ROOT.parent
MARTINE_ROOT = TAKS_ROOT / "martine"
if str(MARTINE_ROOT) not in sys.path:
    sys.path.insert(0, str(MARTINE_ROOT))

from prompting import render_prompts
from llm_decision import fallback_decision

from martine.llm.bedrock_adapter import MartineLlm
from martine_server.agent_loop import AgentLoop
from martine_server.run_context import RunContext
from martine_server.output_validation import parse_structured_json


class ReplayTraceWriter:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _safe_name(self, name: str) -> str:
        s = str(name or "").strip().replace("/", "_")
        return s or "unnamed"

    def write_text(self, name: str, text: str) -> None:
        p = self.root / self._safe_name(name)
        p.write_text(str(text or ""), encoding="utf-8")

    def write_json(self, name: str, obj: Any) -> None:
        p = self.root / self._safe_name(name)
        p.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def append_event(self, kind: str, payload: Any) -> None:
        p = self.root / "events.jsonl"
        row = {"kind": str(kind or ""), "payload": payload}
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _packet_language(packet: Dict[str, Any]) -> str:
    agent = dict(packet.get("agent") or {})
    lp = str(agent.get("language_profile") or agent.get("language") or "").strip().lower()
    return "sv" if lp.startswith("sv") else "en"


def _packet_callsign(packet: Dict[str, Any]) -> str:
    agent = dict(packet.get("agent") or {})
    return str(agent.get("callsign") or "UNKNOWN").strip() or "UNKNOWN"


def _final_format_for_replay() -> str:
    return (
        'Return action="final". '
        'final_json MUST be a replay decision object with exactly this shape at top level: {"work":[...]} '
        "where each work item uses the replay runtime actions and params schema. "
        "Do not put explanatory prose inside final_json. "
        "Keep final_text empty unless absolutely necessary."
    )


def _augment_system_prompt(system_prompt: str) -> str:
    extra = """
Replay-specific rules:
- You are deciding work for a simulated tactical unit in TAKS Replay.
- You may use available tools when they help you produce a better tactical decision.
- Prefer tools for position, contacts, nearby units, terrain/doctrine/current state if available.
- Your final answer MUST be operational work items only, not commentary.
- Keep plans executable by the replay runtime.
- Valid runtime actions are:
  llm_replan_from_inbox, llm_replan_from_deadline, llm_replan_from_world_change,
  send_message, move_unit, change_posture, observe_area, hold_position, report_status.
- For move_unit use params.lat/lon or params.destination_lat/destination_lon.
- For hold_position use params.lat/lon when holding a specific point.
- For send_message/report_status include recipient and message/content as appropriate.
- Be conservative and valid over creative.
""".strip()
    base = str(system_prompt or "").rstrip()
    return base + "\n\n" + extra + "\n"


def _extract_decision_obj(loop_result: Any) -> Dict[str, Any] | None:
    answer_json = getattr(loop_result, "answer_json", None)
    if isinstance(answer_json, dict):
        return answer_json

    answer_text = str(getattr(loop_result, "answer_text", "") or "").strip()
    if not answer_text:
        return None

    try:
        obj = parse_structured_json(answer_text)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass

    try:
        obj = json.loads(answer_text)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass

    return None


def run_model(
    *,
    packet: Dict[str, Any],
    temperature: float,
    max_tokens: int,
    seed: int,
    system_prompt_override: Optional[str] = None,
    user_prompt_override: Optional[str] = None,
    full_prompt_override: Optional[str] = None,
) -> Dict[str, Any]:
    llm = MartineLlm()

    if full_prompt_override is not None:
        system_prompt = system_prompt_override or ""
        user_prompt = user_prompt_override or ""
        full_prompt = full_prompt_override
    elif system_prompt_override is not None or user_prompt_override is not None:
        system_prompt = system_prompt_override or ""
        user_prompt = user_prompt_override or ""
        full_prompt = system_prompt.rstrip() + "\n\n" + user_prompt.rstrip() + "\n"
    else:
        prompts = render_prompts(packet)
        system_prompt = prompts["system_prompt"]
        user_prompt = prompts["user_prompt"]
        full_prompt = prompts["full_prompt"]

    callsign = _packet_callsign(packet)
    language = _packet_language(packet)
    run_id = f"replay-{callsign.lower()}-{uuid.uuid4().hex[:12]}"
    trace_root = Path("/opt/tak/replay/state/agents") / callsign / "martine_trace" / run_id

    ctx = RunContext(
        client="replay",
        workload="replay_unit_decision",
        run_id=run_id,
        state_root="/opt/tak/replay/state",
        trace_root=str(trace_root),
        language=language,
        output_schema="replay_decision_v1",
        max_turns=6,
        max_tool_calls=6,
        max_output_tokens=int(max_tokens),
        allow_repair_turn=True,
        purpose_prefix="replay",
        sender_uid=callsign,
        sender_callsign=callsign,
        extras={
            "replay_packet": packet,
            "replay_callsign": callsign,
        },
    )

    trace = ReplayTraceWriter(trace_root)
    loop = AgentLoop(ctx=ctx, trace=trace)

    try:
        loop_result = loop.run(
            system_prompt=_augment_system_prompt(system_prompt),
            user_input=user_prompt,
            final_format=_final_format_for_replay(),
        )
        decision_obj = _extract_decision_obj(loop_result)

        if isinstance(decision_obj, dict) and "work" in decision_obj:
            text = json.dumps(decision_obj, ensure_ascii=False, indent=2)
            info = llm.info()
            return {
                "ok": True,
                "text": text,
                "provider": info.get("provider"),
                "model": info.get("model"),
                "url": info.get("url"),
                "http_status": None,
                "body_bytes": len(text.encode("utf-8")),
                "error": "" if getattr(loop_result, "ok", False) else getattr(loop_result, "error", ""),
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "full_prompt": full_prompt,
                "raw": {
                    "agent_loop_ok": bool(getattr(loop_result, "ok", False)),
                    "agent_loop_error": getattr(loop_result, "error", ""),
                    "turns": getattr(loop_result, "turns", None),
                    "tool_results": getattr(loop_result, "tool_results", None),
                    "trace_root": str(trace_root),
                },
            }

        reason = getattr(loop_result, "error", "") or "missing_or_invalid_final_json_from_agent_loop"
        fallback = fallback_decision(packet, f"martine_agent_loop_failed: {reason}")
        text = json.dumps(fallback, ensure_ascii=False, indent=2)
        info = llm.info()
        return {
            "ok": True,
            "text": text,
            "provider": info.get("provider"),
            "model": info.get("model"),
            "url": info.get("url"),
            "http_status": None,
            "body_bytes": len(text.encode("utf-8")),
            "error": f"martine_agent_loop_failed: {reason}",
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "full_prompt": full_prompt,
            "raw": {
                "agent_loop_ok": bool(getattr(loop_result, "ok", False)),
                "agent_loop_error": getattr(loop_result, "error", ""),
                "turns": getattr(loop_result, "turns", None),
                "tool_results": getattr(loop_result, "tool_results", None),
                "trace_root": str(trace_root),
                "used_fallback": True,
            },
        }

    except Exception as e:
        fallback = fallback_decision(packet, f"martine_agent_loop_exception: {type(e).__name__}: {e}")
        text = json.dumps(fallback, ensure_ascii=False, indent=2)
        info = llm.info()
        return {
            "ok": True,
            "text": text,
            "provider": info.get("provider"),
            "model": info.get("model"),
            "url": info.get("url"),
            "http_status": None,
            "body_bytes": len(text.encode("utf-8")),
            "error": f"{type(e).__name__}: {e}",
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "full_prompt": full_prompt,
            "raw": {
                "agent_loop_ok": False,
                "agent_loop_error": f"{type(e).__name__}: {e}",
                "trace_root": str(trace_root),
                "used_fallback": True,
            },
        }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--packet", required=True, help="Path to JSON packet")
    ap.add_argument("--temperature", type=float, default=0.2)
    ap.add_argument("--max-tokens", type=int, default=300)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--show-meta", action="store_true")
    ap.add_argument("--show-prompts", action="store_true")
    args = ap.parse_args()

    packet = json.loads(Path(args.packet).read_text(encoding="utf-8"))

    result = run_model(
        packet=packet,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        seed=args.seed,
    )

    if args.show_meta:
        meta = {
            "ok": result["ok"],
            "provider": result["provider"],
            "model": result["model"],
            "url": result["url"],
            "http_status": result["http_status"],
            "body_bytes": result["body_bytes"],
            "error": result["error"],
            "trace_root": (result.get("raw") or {}).get("trace_root"),
        }
        print(json.dumps(meta, ensure_ascii=False, indent=2))
        print()

    if args.show_prompts:
        print("SYSTEM PROMPT")
        print("=" * 80)
        print(result["system_prompt"].rstrip())
        print()
        print("USER PROMPT")
        print("=" * 80)
        print(result["user_prompt"].rstrip())
        print()
        print("FULL PROMPT")
        print("=" * 80)
        print(result["full_prompt"].rstrip())
        print()

    text = result["text"]
    sys.stdout.write(text)
    if text and not text.endswith("\n"):
        sys.stdout.write("\n")


if __name__ == "__main__":
    main()
