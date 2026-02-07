from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional

AGENT_PROTOCOL_VERSION = "taks.llm.agent.v1"


@dataclass
class LLMAgentStep:
    protocol: str
    action: str                 # "query" | "final" | "clarify"
    sql: Optional[str] = None
    answer: Optional[str] = None
    title: Optional[str] = None
    render: Optional[Any] = None


def format_json(obj: Any) -> str:
    return json.dumps(
        obj,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )


def parse_agent_json(obj: dict[str, Any]) -> LLMAgentStep:
    """
    Strict parser. Raises ValueError on any violation.
    """
    if not isinstance(obj, dict):
        raise ValueError("agent response must be a JSON object")

    proto = obj.get("protocol")
    if proto != AGENT_PROTOCOL_VERSION:
        raise ValueError(f"invalid protocol: {proto!r}")

    action = obj.get("action")
    if action not in ("query", "final", "clarify"):
        raise ValueError(f"invalid action: {action!r}")

    return LLMAgentStep(
        protocol=proto,
        action=action,
        sql=obj.get("sql"),
        answer=obj.get("answer"),
        title=obj.get("title"),
        render=obj.get("render"),
    )

