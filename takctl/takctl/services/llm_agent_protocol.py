from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional


AGENT_PROTOCOL_VERSION = "taks.llm.agent.v1"


def _as_str(x: Any) -> str:
    return "" if x is None else str(x)


@dataclass
class LLMAgentStep:
    """
    Strict JSON contract between takctl and the LLM.

    The LLM MUST return a JSON object with:
      - protocol: "taks.llm.agent.v1"
      - action: "query" | "final" | "clarify"
      - sql: required if action == "query"
      - answer: required if action == "final"
      - title: optional
      - render: optional hint object (ignored for now; deterministic render)
    """
    protocol: str
    action: str
    sql: str = ""
    answer: str = ""
    title: str = ""
    render: Optional[dict[str, Any]] = None

    @staticmethod
    def from_obj(obj: Any) -> "LLMAgentStep":
        if not isinstance(obj, dict):
            raise ValueError("agent step must be a JSON object")

        protocol = _as_str(obj.get("protocol")).strip()
        action = _as_str(obj.get("action")).strip().lower()

        if protocol != AGENT_PROTOCOL_VERSION:
            raise ValueError(f"protocol must be {AGENT_PROTOCOL_VERSION!r}")

        if action not in ("query", "final", "clarify"):
            raise ValueError("action must be one of: query|final|clarify")

        step = LLMAgentStep(
            protocol=protocol,
            action=action,
            sql=_as_str(obj.get("sql")).strip(),
            answer=_as_str(obj.get("answer")).strip(),
            title=_as_str(obj.get("title")).strip(),
            render=obj.get("render") if isinstance(obj.get("render"), dict) else None,
        )

        if step.action == "query" and not step.sql:
            raise ValueError("sql is required when action=query")

        if step.action == "final" and not step.answer:
            raise ValueError("answer is required when action=final")

        return step


def format_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True)

