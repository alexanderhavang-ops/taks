from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from tak_installer.config_seed import BOOTSTRAP_CONFIG_DIRS, materialize_component_dir_once
from tak_installer.util import log

DST_ROOT = Path("/opt/tak/tools/martine")
DST_CONF_D = DST_ROOT / "conf.d"
DST_CONFMETA = DST_ROOT / "confmeta"
SRC_ROOT = Path("martine")

WHISPER_PROMPT_NAME = "whisper_prompt.sv.txt"


def _ensure_clean_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def _install_confmeta(src_confmeta: Path, dst_confmeta: Path) -> int:
    _ensure_clean_dir(dst_confmeta)

    if not src_confmeta.exists():
        return 0

    n = 0
    for src in sorted(src_confmeta.iterdir()):
        if not src.is_file():
            continue
        if src.name.startswith("."):
            continue
        if src.suffix not in {".json", ".txt"}:
            continue

        dst = dst_confmeta / src.name
        shutil.copy2(src, dst)
        n += 1

    return n


def _install_whisper_prompt(src_confmeta: Path, dst_conf_d: Path) -> bool:
    src = src_confmeta / WHISPER_PROMPT_NAME
    if not src.is_file():
        return False

    dst_conf_d.mkdir(parents=True, exist_ok=True)
    dst = dst_conf_d / WHISPER_PROMPT_NAME
    shutil.copy2(src, dst)
    dst.chmod(0o640)
    return True


def apply(ctx) -> None:
    src_root = Path(ctx.repo_root) / SRC_ROOT
    src_conf_d = src_root / "conf.d"
    src_confmeta = src_root / "confmeta"

    DST_ROOT.mkdir(parents=True, exist_ok=True)
    DST_CONF_D.mkdir(parents=True, exist_ok=True)

    n_conf = materialize_component_dir_once(
        src_dir=src_conf_d,
        bootstrap_dirs=BOOTSTRAP_CONFIG_DIRS,
        dst_dir=DST_CONF_D,
        mode=0o640,
    )
    n_meta = _install_confmeta(src_confmeta, DST_CONFMETA)
    prompt_installed = _install_whisper_prompt(src_confmeta, DST_CONF_D)

    legacy = DST_ROOT / "martine.conf"
    if legacy.exists():
        legacy.unlink()

    subprocess.run(["chown", "-R", "tak:tak", str(DST_ROOT)], check=False)
    log.info(
        "martine-config: materialized %s runtime conf.d/*.conf, installed %s confmeta files, whisper_prompt=%s",
        n_conf,
        n_meta,
        "yes" if prompt_installed else "no",
    )


class _Action:
    ID = "martine-config"

    def inspect(self, ctx) -> int:
        src_root = Path(ctx.repo_root) / SRC_ROOT
        print("Inspecting martine-config action...")
        print(f"  src conf.d: {src_root / 'conf.d'}")
        print(f"  dst conf.d: {DST_CONF_D}")
        print(f"  src confmeta: {src_root / 'confmeta'}")
        print(f"  dst confmeta: {DST_CONFMETA}")
        print(f"  whisper prompt dst: {DST_CONF_D / WHISPER_PROMPT_NAME}")
        return 0

    def apply(self, ctx) -> int:
        print("Applying martine-config action...")
        apply(ctx)
        return 0


ACTION = _Action()
