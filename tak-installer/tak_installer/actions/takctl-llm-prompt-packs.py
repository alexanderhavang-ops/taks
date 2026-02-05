from __future__ import annotations

from pathlib import Path

from tak_installer.context import Context
from tak_installer.actions.base import Action


class TakctlLLMPromptPacks(Action):
    """
    Deploy LLM prompt packs into takctl runtime.

    Logic will be added later. For now, this action only establishes
    installer ownership and destination paths.
    """

    ID = "takctl.llm-prompt-packs"

    def apply(self, ctx: Context) -> None:
        src_defaults = ctx.repo_root / "llm-infra" / "llm" / "prompt-packs"
        dst_runtime = Path("/opt/tak/tools/takctl/llm/prompt-packs")

        self.log.info("LLM prompt packs (stub)")
        self.log.info("defaults: %s", src_defaults)
        self.log.info("runtime:  %s", dst_runtime)

        dst_runtime.mkdir(parents=True, exist_ok=True)
