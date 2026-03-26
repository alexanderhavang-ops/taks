from __future__ import annotations

from typing import Any, Dict, Optional
import inspect

from takctl.services.llm2.llm_client import LlmClient


class MartineLlm:
    """
    Thin Martine wrapper around existing TAKCTL LLM transport.

    Important:
    - Keep provider/http details inside takctl.services.llm2.llm_client.LlmClient
    - Keep MCP/tool orchestration OUTSIDE this class
    - Be tolerant to LlmClient signature drift between takctl versions
    """

    def __init__(self, env_path: Optional[str] = None) -> None:
        sig = inspect.signature(LlmClient.__init__)
        if "env_path" in sig.parameters:
            self.client = LlmClient(env_path=env_path)
        else:
            self.client = LlmClient()

    def complete_text(
        self,
        *,
        prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 800,
        seed: Optional[int] = None,
    ) -> Dict[str, Any]:
        return self.client.complete_text(
            prompt=prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            seed=seed,
        )

    def info(self) -> Dict[str, Any]:
        return {
            "provider": getattr(self.client, "provider", ""),
            "url": getattr(self.client, "url", ""),
            "model": getattr(self.client, "model", ""),
            "aws_region": getattr(self.client, "aws_region", ""),
            "bedrock_model_id": getattr(self.client, "bedrock_model_id", ""),
            "env_path": getattr(self.client, "env_path", ""),
        }
