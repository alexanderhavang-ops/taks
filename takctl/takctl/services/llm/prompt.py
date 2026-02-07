from __future__ import annotations

import json
from typing import Any, Optional

from takctl.services.llm.protocol import AGENT_PROTOCOL_VERSION


def agent_system_prompt(*, max_rows: int) -> str:
    # Strict “constitution” — JSON is non-negotiable.
    return f"""
You are a strict JSON agent for a PostgreSQL-backed TAK system.

ABSOLUTE RULES:
- You MUST return ONLY valid JSON. No prose. No markdown. No code fences. No leading/trailing text.
- Your JSON MUST be a single object with EXACTLY these top-level keys:
  - protocol
  - action
  - sql
  - answer
  - title
  - render

Where:
- protocol MUST be "{AGENT_PROTOCOL_VERSION}"
- action MUST be one of: "query", "final", "clarify"
- If action="query": sql MUST contain ONE read-only query (PostgreSQL), starting with SELECT or WITH, and must NOT contain ';'
- If action="final": answer MUST contain the final answer for the user (clear, concise)
- title is optional (string)
- render is optional (object) but must exist (use null if unused)

DATABASE SAFETY:
- Read-only only.
- Prefer LIMIT {int(max_rows)} unless the question inherently needs fewer.
- If you need schema discovery, use information_schema and pg_catalog.
- Do not assume table names; discover.

BEHAVIOR:
- If you do not have enough info, use action="query" with schema discovery SQL.
- If the user question is ambiguous, use action="clarify" with a short question in "answer" and empty sql.

Remember: ONLY JSON.
""".strip()


def build_agent_prompt(
    *,
    user_prompt: str,
    history: list[dict[str, Any]],
    last_db_result: Optional[dict[str, Any]],
    max_rows: int,
    schema_bundle: Optional[dict[str, Any]] = None,
) -> str:
    """
    Builds the single prompt string we send to the LLM.
    We always include a CONTEXT_JSON envelope so we can grow it later (schema, policies, etc.)
    without changing the “constitution”.
    """
    sys = agent_system_prompt(max_rows=max_rows)

    payload: dict[str, Any] = {
        "user_prompt": user_prompt,
        "history": history,
        "last_db_result": last_db_result,
        "schema": schema_bundle,  # optional (we’ll wire this soon)
        "instructions": {
            "return_only_json": True,
            "protocol": AGENT_PROTOCOL_VERSION,
        },
    }

    return sys + "\n\n" + "CONTEXT_JSON:\n" + json.dumps(
        payload, ensure_ascii=False, indent=2, sort_keys=True
    )

