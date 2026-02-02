from __future__ import annotations

import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from tak_installer.util import sha256_path, diff_text


def _run(cmd: list[str], check: bool = True) -> None:
    subprocess.run(cmd, check=check)


def _sudo_install(src_text: str, dst: Path, mode: str = "0644") -> None:
    # Write temp file in /tmp then sudo install into /etc (no permission issues)
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".tmp") as tf:
        tf.write(src_text)
        tmp = tf.name
    try:
        _run(["sudo", "install", "-m", mode, tmp, str(dst)], check=True)
    finally:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass


@dataclass(frozen=True)
class SystemdUnit:
    name: str
    src: Path
    dst: Path

    def inspect(self) -> dict[str, str]:
        out: dict[str, str] = {}
        out["src"] = str(self.src)
        out["dst"] = str(self.dst)

        if not self.src.is_file():
            out["status"] = "missing-src"
            return out

        out["src_sha256"] = sha256_path(self.src)

        if self.dst.exists():
            out["dst_sha256"] = sha256_path(self.dst)
            if out["dst_sha256"] == out["src_sha256"]:
                out["status"] = "up-to-date"
            else:
                out["status"] = "differs"
                out["diff"] = diff_text(self.dst, self.src)
        else:
            out["status"] = "not-installed"

        return out

    def apply(self) -> None:
        if not self.src.is_file():
            raise FileNotFoundError(f"source unit not found: {self.src}")

        src_text = self.src.read_text(encoding="utf-8")

        before_sha = sha256_path(self.dst) if self.dst.exists() else ""
        # Ensure parent exists (privileged path)
        _run(["sudo", "mkdir", "-p", str(self.dst.parent)], check=True)

        _sudo_install(src_text, self.dst, mode="0644")

        after_sha = sha256_path(self.dst) if self.dst.exists() else ""
        changed = (before_sha != after_sha)

        _run(["sudo", "systemctl", "daemon-reload"], check=True)

        # Restart only if unit changed; also don't brick apply if restart fails.
        if changed:
            svc = self.name  # keep full name
            _run(["sudo", "systemctl", "restart", svc], check=False)
