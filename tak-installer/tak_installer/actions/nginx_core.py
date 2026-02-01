from __future__ import annotations

import os
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from tak_installer.engine import Context
from tak_installer.util import sha256_path, diff_text


def _run(cmd: list[str], check: bool = True) -> None:
    subprocess.run(cmd, check=check)


def _sudo_install_text(dst: Path, content: str, mode: str = "0644") -> None:
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".tmp") as tf:
        tf.write(content)
        tmp = tf.name
    try:
        _run(["sudo", "install", "-m", mode, tmp, str(dst)], check=True)
    finally:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass


def _ts() -> str:
    return datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")


@dataclass(frozen=True)
class _File:
    name: str
    src: Path
    dst: Path

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

    def backup_path(self) -> Path:
        return self.dst.with_name(self.dst.name + f".bak.{_ts()}")

    def backup(self) -> Path | None:
        if self.dst.exists():
            bp = self.backup_path()
            _run(["sudo", "cp", "-a", str(self.dst), str(bp)], check=True)
            return bp
        return None

    def restore(self, backup: Path) -> None:
        _run(["sudo", "cp", "-a", str(backup), str(self.dst)], check=True)

    def apply(self) -> bool:
        before = sha256_path(self.dst) if self.dst.exists() else ""
        content = self.src.read_text(encoding="utf-8")

        _run(["sudo", "mkdir", "-p", str(self.dst.parent)], check=True)
        _sudo_install_text(self.dst, content, mode="0644")

        after = sha256_path(self.dst) if self.dst.exists() else ""
        return before != after


@dataclass(frozen=True)
class _Action:
    ID: str = "nginx.core"

    def _files(self, ctx: Context) -> list[_File]:
        repo = ctx.repo_root
        return [
            _File(
                name="nginx.conf",
                src=repo / "infra" / "nginx" / "core" / "nginx.conf",
                dst=Path("/etc/nginx/nginx.conf"),
            ),
            _File(
                name="mime.types",
                src=repo / "infra" / "nginx" / "core" / "mime.types",
                dst=Path("/etc/nginx/mime.types"),
            ),
            _File(
                name="conf.d/00-logformats.conf",
                src=repo / "infra" / "nginx" / "core" / "conf.d" / "00-logformats.conf",
                dst=Path("/etc/nginx/conf.d/00-logformats.conf"),
            ),
        ]
    def inspect(self, ctx: Context) -> int:
        print("Nginx core (/etc/nginx/nginx.conf, mime.types)")
        for f in self._files(ctx):
            info = f.inspect()
            print(f"  - {f.name}")
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
        # Backup first
        backups: list[tuple[_File, Path]] = []
        for f in self._files(ctx):
            bp = f.backup()
            if bp is not None:
                backups.append((f, bp))

        changed_any = False
        try:
            for f in self._files(ctx):
                changed_any = f.apply() or changed_any

            # Validate
            _run(["sudo", "nginx", "-t"], check=True)

            # Reload
            _run(["sudo", "systemctl", "reload", "nginx"], check=True)

            print(f"applied: nginx.core (changed={str(bool(changed_any)).lower()})")
            return 0

        except subprocess.CalledProcessError as e:
            print(f"ERROR: nginx.core failed: {e}")
            print("ERROR: rolling back nginx core files from backups...")

            for f, bp in backups:
                try:
                    f.restore(bp)
                except Exception as re:
                    print(f"ERROR: rollback failed for {f.dst}: {re}")

            # Re-test after rollback to give a clear signal
            try:
                _run(["sudo", "nginx", "-t"], check=False)
            except Exception:
                pass

            return 2


ACTION = _Action()
