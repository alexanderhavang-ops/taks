from __future__ import annotations

import uuid
from typing import Any, Optional

from takctl.infra.db import DB
from takctl.services.llm.client import LLMClient
from takctl.services.llm.prompt import build_agent_prompt
from takctl.services.llm.protocol import AGENT_PROTOCOL_VERSION, LLMAgentStep
from takctl.services.llm.sql_guard import looks_like_sql
from takctl.services.llm_extract import extract_json_from_text


def _rows_to_json(
    rows: list[tuple],
    *,
    max_rows: int,
    max_cell_chars: int,
) -> list[list[str]]:
    out: list[list[str]] = []
    for r in rows[:max_rows]:
        rr: list[str] = []
        for cell in r:
            s = "" if cell is None else str(cell)
            rr.append(s[:max_cell_chars])
        out.append(rr)
    return out


def run_agent_loop(
    *,
    llm: LLMClient,
    db: DB,
    user_prompt: str,
    max_steps: int = 6,
    max_rows: int = 80,
    max_cell_chars: int = 400,
    llm_max_tokens: int = 800,
    llm_temperature: float = 0.0,
    schema_bundle: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Deterministic JSON-in / JSON-out agent loop.

    Returns:
      {
        "mode": "agent",
        "protocol": "...",
        "steps": [...],
        "final": {...} | null,
      }
    """
    history: list[dict[str, Any]] = []
    last_db_result: Optional[dict[str, Any]] = None
    final_step: Optional[dict[str, Any]] = None

    session_id = f"llmchat-{uuid.uuid4().hex[:10]}"

    for step_idx in range(1, max_steps + 1):
        prompt = build_agent_prompt(
            user_prompt=user_prompt,
            history=history,
            last_db_result=last_db_result,
            max_rows=max_rows,
            schema_bundle=schema_bundle,
        )

        raw = llm.completions_text(
            prompt,
            max_tokens=llm_max_tokens,
            temperature=llm_temperature,
        )

        extracted, extract_err, candidate = extract_json_from_text(raw)

        if extracted is None:
            history.append(
                {
                    "step": step_idx,
                    "error": "llm_output_not_json",
                    "detail": extract_err,
                    "candidate": candidate,
                }
            )
            continue

        step = LLMAgentStep.from_dict(extracted)

        if step.protocol != AGENT_PROTOCOL_VERSION:
            history.append(
                {
                    "step": step_idx,
                    "error": "protocol_mismatch",
                    "got": step.protocol,
                }
            )
            continue

        if step.action == "clarify":
            final_step = step.to_dict()
            break

        if step.action == "final":
            final_step = step.to_dict()
            break

        if step.action != "query":
            history.append(
                {
                    "step": step_idx,
                    "error": "invalid_action",
                    "action": step.action,
                }
            )
            continue

        sql = (step.sql or "").strip()
        if not looks_like_sql(sql):
            history.append(
                {
                    "step": step_idx,
                    "sql_rejected": True,
                    "sql": sql,
                    "reason": "sql_guard_rejected",
                }
            )
            continue

        try:
            rows = db.fetchall(sql)
            last_db_result = {
                "sql": sql,
                "rows": _rows_to_json(
                    rows,
                    max_rows=max_rows,
                    max_cell_chars=max_cell_chars,
                ),
            }
            history.append(
                {
                    "step": step_idx,
                    "sql_ok": True,
                    "row_count": len(last_db_result["rows"]),
                }
            )
        except Exception as e:
            last_db_result = {
                "sql": sql,
                "error": f"{type(e).__name__}: {e}",
            }
            history.append(
                {
                    "step": step_idx,
                    "sql_error": True,
                    "error": last_db_result["error"],
                }
            )

    return {
        "mode": "agent",
        "protocol": AGENT_PROTOCOL_VERSION,
        "session_id": session_id,
        "steps": history,
        "final": final_step,
    }

