from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from tak_installer.util import log

DST_WEB_DIR = Path("/opt/tak/tools/takctl/web")

RSYNC_EXCLUDES = [
    "--exclude=__pycache__/",
    "--exclude=*.pyc",
    "--exclude=*.pyo",
    "--exclude=*.swp",
    "--exclude=*.swo",
    "--exclude=*~",
]


def _src_web_dir(ctx) -> Path:
    return Path(ctx.repo_root) / "takctl" / "web"


def _run(cmd: list[str]) -> None:
    p = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if p.returncode != 0:
        raise RuntimeError(f"command failed rc={p.returncode}:\n{' '.join(cmd)}\n\n{p.stdout}")
    if p.stdout.strip():
        log.info(p.stdout.strip())


def apply(ctx) -> None:
    src_web_dir = _src_web_dir(ctx)

    log.info("takctl-web-assets: syncing entire web directory to runtime")
    log.info("  source:  %s", src_web_dir)
    log.info("  runtime: %s", DST_WEB_DIR)

    if not src_web_dir.exists():
        raise RuntimeError(f"takctl web directory missing: {src_web_dir}")

    DST_WEB_DIR.mkdir(parents=True, exist_ok=True)

    rsync = shutil.which("rsync")
    if not rsync:
        raise RuntimeError("rsync not found; install rsync or add a correct mirror implementation")

    cmd = [
        rsync,
        "-r",
        "--delete",
        "--no-owner",
        "--no-group",
        "--no-perms",
        "--chmod=Du=rwx,Dgo=rx,Fu=rw,Fgo=r",
        *RSYNC_EXCLUDES,
        f"{src_web_dir}/",
        f"{DST_WEB_DIR}/",
    ]
    _run(cmd)

    subprocess.run(["chown", "-R", "tak:tak", str(DST_WEB_DIR)], check=False)

    log.info("takctl-web-assets: sync complete (rsync install-policy)")


class _Action:
    ID = "takctl-web-assets"

    def inspect(self, ctx) -> int:
        log.info("Inspecting %s action...", self.ID)
        log.info("  source: %s", _src_web_dir(ctx))
        log.info("  runtime: %s", DST_WEB_DIR)
        return 0

    def apply(self, ctx) -> int:
        log.info("Applying %s action...", self.ID)
        apply(ctx)
        return 0


ACTION = _Action()
