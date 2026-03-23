from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from tak_installer.engine import Context
from tak_installer.log import get_logger

log = get_logger(__name__)


def _src(ctx: Context) -> Path:
    return ctx.repo_root / "takctl" / "llm-infra"


DST = Path("/opt/tak/tools/takctl/llm-infra")


def _sync_tree(src: Path, dst: Path) -> None:
    if not src.exists():
        raise RuntimeError(f"missing llm-infra source dir: {src}")

    dst.parent.mkdir(parents=True, exist_ok=True)

    # installer-owned: replace entirely each apply (simple + deterministic)
    if dst.exists():
        shutil.rmtree(dst)

    shutil.copytree(src, dst)


@dataclass
class TakctlLlm2InfraAction:
    def inspect(self, ctx: Context) -> int:
        src = _src(ctx)
        log.info("Inspecting takctl.llm2-infra action...")
        log.info("  src: %s", src)
        log.info("  dst: %s", DST)
        return 0

    def apply(self, ctx: Context) -> int:
        src = _src(ctx)
        log.info("Applying takctl.llm2-infra action...")
        log.info("  src: %s", src)
        log.info("  dst: %s", DST)

        _sync_tree(src, DST)
        subprocess.run(["chown", "-R", "tak:tak", str(DST)], check=False)

        log.info("takctl.llm2-infra: ready")
        return 0


class _Action:
    ID = "takctl.llm2-infra"

    def inspect(self, ctx: Context) -> int:
        return TakctlLlm2InfraAction().inspect(ctx)

    def apply(self, ctx: Context) -> int:
        return TakctlLlm2InfraAction().apply(ctx)


ACTION = _Action()
