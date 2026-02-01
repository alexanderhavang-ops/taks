from __future__ import annotations

import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from tak_installer.engine import Context
from tak_installer.util import sha256_path, diff_text


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def _sudo_install_text(dst: Path, content: str, mode: str = "0644") -> None:
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".tmp") as tf:
        tf.write(content)
        tmp = tf.name
    try:
        _run(["sudo", "install", "-m", mode, tmp, str(dst)])
    finally:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass


@dataclass(frozen=True)
class NginxSnippet:
    src: Path
    dst: Path
    name: str

    def inspect(self) -> dict[str, str]:
        out: dict[str, str] = {"name": self.name, "src": str(self.src), "dst": str(self.dst)}
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
            out["dst_sha256"] = ""
            out["status"] = "not-installed"
        return out

    def apply(self) -> bool:
        # Returns True if changed
        if not self.src.is_file():
            raise FileNotFoundError(f"missing src: {self.src}")

        before = sha256_path(self.dst) if self.dst.exists() else ""
        content = self.src.read_text(encoding="utf-8")

        _run(["sudo", "mkdir", "-p", str(self.dst.parent)])
        _sudo_install_text(self.dst, content, mode="0644")

        after = sha256_path(self.dst) if self.dst.exists() else ""
        return before != after


@dataclass(frozen=True)
class _Action:
    ID: str = "nginx.snippets.core"

    def _snips(self, ctx: Context) -> list[NginxSnippet]:
        repo = ctx.repo_root
        return [
            NginxSnippet(
                name="ssl-common.conf",
                src=repo / "infra" / "nginx" / "snippets" / "ssl-common.conf",
                dst=Path("/etc/nginx/snippets/ssl-common.conf"),
            ),
            NginxSnippet(
                name="deny-dotfiles.conf",
                src=repo / "infra" / "nginx" / "snippets" / "deny-dotfiles.conf",
                dst=Path("/etc/nginx/snippets/deny-dotfiles.conf"),
            ),
            NginxSnippet(
                name="acme-challenge.conf",
                src=repo / "infra" / "nginx" / "snippets" / "acme-challenge.conf",
                dst=Path("/etc/nginx/snippets/acme-challenge.conf"),
            ),
        ]

    def inspect(self, ctx: Context) -> int:
        print("Nginx core snippets")
        for s in self._snips(ctx):
            info = s.inspect()
            print(f"  - {s.name}")
            print(f"    src: {info['src']}")
            print(f"    dst: {info['dst']}")
            print(f"    src sha256: {info.get('src_sha256','')}")
            print(f"    dst sha256: {info.get('dst_sha256','')}")
            print(f"    status: {info.get('status')}")
            if info.get("status") == "differs":
                print("    diff:")
                print(info.get("diff") or "(no diff)")
        print("  dry-run: no changes performed.")
        return 0

    def apply(self, ctx: Context) -> int:
        changed_any = False
        for s in self._snips(ctx):
            changed = s.apply()
            changed_any = changed_any or changed

        _run(["sudo", "nginx", "-t"])
        _run(["sudo", "systemctl", "reload", "nginx"])

        print(f"applied: nginx.snippets.core (changed={str(bool(changed_any)).lower()})")
        return 0


ACTION = _Action()
