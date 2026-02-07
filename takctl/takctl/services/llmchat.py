from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from takctl.infra.db import DB

from takctl.services.llm.client import build_llm_client_from_env, LLMClient
from takctl.services.llm_agent import run_agent_loop  # compatibility shim


@dataclass
class LLMChat:
    llm: LLMClient

    def ask_plain(self, prompt: str, *, max_tokens: int = 512, temperature: float = 0.2) -> dict[str, Any]:
        """
        Fastest dev path: prompt -> LLM -> raw text.
        (No schema, no JSON enforcement.)
        """
        text = self.llm.completions_text(
            prompt.strip(),
            max_tokens=int(max_tokens),
            temperature=float(temperature),
            timeout_sec=60.0,
        )
        return {
            "mode": "plain",
            "llm_url": self.llm.llm_url,
            "model": self.llm.model,
            "prompt": prompt,
            "answer": (text or "").strip(),
        }

    def ask_agent(
        self,
        *,
        db: DB,
        question: str,
        max_steps: int = 6,
        max_rows: int = 80,
        schema_bundle: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """
        Agent loop (JSON protocol + SQL execution loop).
        This is the forward path: question -> (LLM JSON -> SQL) -> DB -> back to LLM ... -> final.
        """
        try:
            return run_agent_loop(
                llm=self.llm,
                db=db,
                user_prompt=question,
                max_steps=int(max_steps),
                max_rows=int(max_rows),
                max_cell_chars=400,
                llm_max_tokens=800,
                llm_temperature=0.0,
                schema_bundle=schema_bundle,
            )
        except Exception as e:
            return {
                "schema_version": "taks.renderplan.v1",
                "blocks": [
                    {
                        "type": "markdown",
                        "title": "LLM Chat",
                        "body": f"Agent failed: {type(e).__name__}: {e}",
                    }
                ],
                "datasets": {},
                "meta": {
                    "mode": "agent",
                    "error": f"{type(e).__name__}: {e}",
                    "llm_url": self.llm.llm_url,
                    "model": self.llm.model,
                },
            }


def build_llmchat_from_env() -> LLMChat:
    return LLMChat(llm=build_llm_client_from_env())

