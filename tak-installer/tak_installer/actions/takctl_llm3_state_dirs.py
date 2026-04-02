from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from tak_installer.engine import Context
from tak_installer.log import get_logger

log = get_logger(__name__)
ROOT = Path('/opt/tak/tools/takctl/state/llm3')


@dataclass
class TakctlLlm3StateDirsAction:
    def inspect(self, ctx: Context) -> int:
        log.info('Inspecting takctl.llm3-state-dirs action...')
        log.info('  root: %s', ROOT)
        return 0

    def apply(self, ctx: Context) -> int:
        log.info('Applying takctl.llm3-state-dirs action...')
        for d in (ROOT, ROOT / 'runs', ROOT / 'latest'):
            d.mkdir(parents=True, exist_ok=True)
        subprocess.run(['chown', '-R', 'tak:tak', str(ROOT)], check=False)
        subprocess.run(['chmod', '0755', str(ROOT)], check=False)
        subprocess.run(['chmod', '0755', str(ROOT / 'runs')], check=False)
        subprocess.run(['chmod', '0755', str(ROOT / 'latest')], check=False)
        log.info('takctl.llm3-state-dirs: ready')
        return 0


class _Action:
    ID = 'takctl.llm3-state-dirs'
    def inspect(self, ctx: Context) -> int:
        return TakctlLlm3StateDirsAction().inspect(ctx)
    def apply(self, ctx: Context) -> int:
        return TakctlLlm3StateDirsAction().apply(ctx)

ACTION = _Action()
