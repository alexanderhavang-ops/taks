from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RunContext:
    client: str
    workload: str
    run_id: str
    state_root: str
    trace_root: str
    language: str = 'sv'
    output_schema: str = ''
    max_turns: int = 6
    max_tool_calls: int = 10
    allow_repair_turn: bool = True
    purpose_prefix: str = 'martine'
    sender_uid: str = ''
    sender_callsign: str = ''
    extras: dict[str, Any] = field(default_factory=dict)
