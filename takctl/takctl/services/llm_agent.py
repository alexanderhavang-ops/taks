from __future__ import annotations

from typing import Any, Optional

from takctl.infra.db import DB

# New modular layout (authoritative)
from takctl.services.llm.client import LLMClient
from takctl.services.llm.agent_loop import run_agent_loop as _run_agent_loop


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
    Compatibility shim.

    Keep legacy import path:
      takctl.services.llm_agent.run_agent_loop

    Actual implementation lives in:
      takctl.services.llm.agent_loop.run_agent_loop
    """
    return _run_agent_loop(
        llm=llm,
        db=db,
        user_prompt=user_prompt,
        max_steps=max_steps,
        max_rows=max_rows,
        max_cell_chars=max_cell_chars,
        llm_max_tokens=llm_max_tokens,
        llm_temperature=llm_temperature,
        schema_bundle=schema_bundle,
    )

