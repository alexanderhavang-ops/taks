from __future__ import annotations

import subprocess
from pathlib import Path

from tak_installer.log import get_logger

log = get_logger(__name__)

DST_ROOT = Path("/opt/tak/tools/takctl")

WRITABLE_TREES = [
    DST_ROOT / "conf.d",
    DST_ROOT / "secrets.d",
    DST_ROOT / "state",
]

WRITABLE_FILES = [
    DST_ROOT / "takctl.conf",
    DST_ROOT / "secrets.conf",
]


def _run_best_effort(cmd: list[str]) -> None:
    subprocess.run(cmd, check=False)


def _chmod_tree(root: Path, dir_mode: str, file_mode: str) -> None:
    _run_best_effort(
        ["bash", "-lc", f'find "{root}" -type d -exec chmod {dir_mode} {{}} \\; 2>/dev/null || true']
    )
    _run_best_effort(
        ["bash", "-lc", f'find "{root}" -type f -exec chmod {file_mode} {{}} \\; 2>/dev/null || true']
    )


def apply(ctx) -> None:
    log.info("takctl.runtime-perms: normalizing writable runtime trees")

    for d in WRITABLE_TREES:
        d.mkdir(parents=True, exist_ok=True)
        _run_best_effort(["chown", "-R", "tak:tak", str(d)])
        _chmod_tree(d, "2770", "0660")

    for f in WRITABLE_FILES:
        if not f.exists():
            continue
        _run_best_effort(["chown", "tak:tak", str(f)])
        _run_best_effort(["chmod", "0660", str(f)])

    log.info("takctl.runtime-perms: ready")


class _Action:
    ID = "takctl.runtime-perms"

    def inspect(self, ctx) -> int:
        print(f"Inspecting {self.ID} action...")
        for p in WRITABLE_TREES:
            print(f"tree: {p}")
        for p in WRITABLE_FILES:
            print(f"file: {p}")
        return 0

    def apply(self, ctx) -> int:
        print(f"Applying {self.ID} action...")
        apply(ctx)
        return 0


ACTION = _Action()
