from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from tak_installer.util import log

DST_ROOT = Path("/opt/tak/tools/martine")
DST_CONF_D = DST_ROOT / "conf.d"
DST_CONFMETA = DST_ROOT / "confmeta"
SRC_ROOT = Path("martine")


def _ensure_clean_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def _install_conf_templates(src_conf_d: Path, dst_conf_d: Path) -> None:
    _ensure_clean_dir(dst_conf_d)

    if not src_conf_d.exists():
        return

    for src in sorted(src_conf_d.iterdir()):
        if not src.is_file():
            continue

        name = src.name
        if name.endswith(".conf.template"):
            dst_name = name[:-9]  # strip ".template" -> ".conf"
        elif name.endswith(".conf"):
            dst_name = name
        else:
            continue

        dst = dst_conf_d / dst_name
        dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")


def _install_confmeta(src_confmeta: Path, dst_confmeta: Path) -> None:
    _ensure_clean_dir(dst_confmeta)

    if not src_confmeta.exists():
        return

    for src in sorted(src_confmeta.glob("*.json")):
        dst = dst_confmeta / src.name
        dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")


def apply(ctx) -> None:
    src_root = Path(ctx.repo_root) / SRC_ROOT
    src_conf_d = src_root / "conf.d"
    src_confmeta = src_root / "confmeta"

    DST_ROOT.mkdir(parents=True, exist_ok=True)

    _install_conf_templates(src_conf_d, DST_CONF_D)
    _install_confmeta(src_confmeta, DST_CONFMETA)

    legacy = DST_ROOT / "martine.conf"
    if legacy.exists():
        legacy.unlink()

    subprocess.run(["chown", "-R", "tak:tak", str(DST_ROOT)], check=False)
    log.info("martine-config: installed runtime conf.d/*.conf and confmeta/*.json")


class _Action:
    ID = "martine-config"

    def inspect(self, ctx) -> int:
        print("Inspecting martine-config action...")
        print(f"  src: {Path(ctx.repo_root) / SRC_ROOT / 'conf.d'}")
        print(f"  dst: {DST_CONF_D}")
        print(f"  confmeta dst: {DST_CONFMETA}")
        return 0

    def apply(self, ctx) -> int:
        print("Applying martine-config action...")
        apply(ctx)
        return 0


ACTION = _Action()
