from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from tak_installer.util import log

DST_ROOT = Path('/opt/tak/tools/martine')
DST_CONF_D = DST_ROOT / 'conf.d'
DST_CONFMETA = DST_ROOT / 'confmeta'
SRC_ROOT_REL = Path('martine')


def _copy_dir(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    if src.exists():
        shutil.copytree(src, dst)
    else:
        dst.mkdir(parents=True, exist_ok=True)


def apply(ctx) -> None:
    src_root = Path(ctx.repo_root) / SRC_ROOT_REL
    _copy_dir(src_root / 'conf.d', DST_CONF_D)
    _copy_dir(src_root / 'confmeta', DST_CONFMETA)
    subprocess.run(['chown', '-R', 'tak:tak', str(DST_ROOT)], check=False)
    log.info('martine-config: installed conf.d and confmeta')


class _Action:
    ID = 'martine-config'

    def inspect(self, ctx) -> int:
        print('Inspecting martine-config action...')
        return 0

    def apply(self, ctx) -> int:
        print('Applying martine-config action...')
        apply(ctx)
        return 0


ACTION = _Action()
