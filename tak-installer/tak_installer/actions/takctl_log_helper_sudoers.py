from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

SUDOERS_DST = Path("/etc/sudoers.d/takctl-log-helper")
SUDOERS_TEXT = """Defaults:tak !requiretty
tak ALL=(root) NOPASSWD: /opt/tak/tools/takctl/bin/takctl-log-helper *
"""


def _run(cmd: list[str]) -> tuple[int, str]:
    p = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    return int(p.returncode), (p.stdout or "").rstrip()


def _validate_text(text: str) -> tuple[int, str]:
    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as tf:
        tf.write(text)
        tmp = tf.name
    try:
        return _run(["visudo", "-cf", tmp])
    finally:
        try:
            Path(tmp).unlink(missing_ok=True)
        except Exception:
            pass


@dataclass(frozen=True)
class _Action:
    ID: str = "takctl-log-helper-sudoers"

    def inspect(self, ctx) -> int:
        print(f"Sudoers file: {SUDOERS_DST}")
        print(f"  exists: {str(SUDOERS_DST.exists()).lower()}")
        if SUDOERS_DST.exists():
            try:
                current = SUDOERS_DST.read_text(encoding="utf-8")
            except Exception as e:
                print(f"  read error: {e}")
                return 1
            print(f"  status: {'ok' if current == SUDOERS_TEXT else 'differs'}")
        else:
            print("  status: not installed")
        return 0

    def apply(self, ctx) -> int:
        rc, out = _validate_text(SUDOERS_TEXT)
        if rc != 0:
            print("ERROR: generated sudoers content failed validation")
            print(out)
            return 2

        SUDOERS_DST.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as tf:
            tf.write(SUDOERS_TEXT)
            tmp = tf.name

        try:
            rc, out = _run(["install", "-m", "0440", tmp, str(SUDOERS_DST)])
            if rc != 0:
                print("ERROR: failed to install sudoers file")
                print(out)
                return 3

            rc, out = _run(["visudo", "-cf", str(SUDOERS_DST)])
            if rc != 0:
                print("ERROR: installed sudoers file failed validation")
                print(out)
                return 4

            print("Applied.")
            return 0
        finally:
            try:
                Path(tmp).unlink(missing_ok=True)
            except Exception:
                pass


ACTION = _Action()
