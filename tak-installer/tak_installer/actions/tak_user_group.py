from __future__ import annotations

import subprocess

from tak_installer.util import log


def _run(cmd: list[str]) -> None:
    p = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if p.returncode != 0:
        raise RuntimeError(f"command failed rc={p.returncode}:\n{' '.join(cmd)}\n\n{p.stdout}")
    if p.stdout.strip():
        log.info(p.stdout.strip())


def apply(ctx) -> None:
    if subprocess.run(["getent", "group", "tak"], stdout=subprocess.DEVNULL).returncode != 0:
        _run(["groupadd", "--system", "tak"])

    if subprocess.run(["id", "-u", "tak"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode != 0:
        subprocess.run(["mkdir", "-p", "/opt/tak"], check=True)
        _run([
            "useradd",
            "--system",
            "--gid", "tak",
            "--home", "/opt/tak",
            "--shell", "/usr/sbin/nologin",
            "tak",
        ])


class _Action:
    ID = "tak-user-group"

    def inspect(self, ctx) -> int:
        log.info("Inspecting %s action...", self.ID)
        return 0

    def apply(self, ctx) -> int:
        log.info("Applying %s action...", self.ID)
        apply(ctx)
        return 0


ACTION = _Action()
