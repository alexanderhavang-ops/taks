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


def _sudo_install(dst: Path, content: str, mode: str = "0644") -> None:
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


def _sudo_rm(path: Path) -> None:
    _run(["sudo", "rm", "-f", str(path)])


def _sudo_symlink(link_path: Path, target: Path) -> None:
    _run(["sudo", "ln", "-sfn", str(target), str(link_path)])


@dataclass(frozen=True)
class Nginx8446FrontdoorAction:
    ID = "nginx.8446.frontdoor"

    template: Path

    def _fqdn(self, ctx: Context) -> str:
        fqdn = (ctx.env.get("FQDN") or ctx.env.get("TAKS_FQDN") or "").strip()
        if not fqdn:
            raise RuntimeError("FQDN not set. Provide FQDN env var (or TAKS_FQDN).")
        return fqdn

    def _paths(self, fqdn: str) -> tuple[Path, Path]:
        name = f"tak-{fqdn}-enroll-8446.conf"  # canonical filename
        return (
            Path("/etc/nginx/sites-available") / name,
            Path("/etc/nginx/sites-enabled") / name,
        )

    def _render(self, fqdn: str) -> str:
        return self.template.read_text(encoding="utf-8").replace("__FQDN__", fqdn)

    def _enabled_state(self, enabled: Path) -> str:
        if enabled.is_symlink():
            try:
                return f"symlink -> {enabled.resolve()}"
            except FileNotFoundError:
                return "symlink -> (broken)"
        if enabled.exists():
            return "regular-file"
        return "missing"

    def inspect(self, ctx: Context) -> int:
        fqdn = self._fqdn(ctx)
        available, enabled = self._paths(fqdn)

        print("Nginx 8446 site (front door)")
        print(f"  template:   {self.template}")
        print(f"  available:  {available}")
        print(f"  enabled:    {enabled}")
        print(f"  fqdn:       {fqdn}")

        if not self.template.is_file():
            print("  status: missing-template")
            return 1

        rendered = self._render(fqdn)

        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".conf") as tf:
            tf.write(rendered)
            tmp = Path(tf.name)

        try:
            desired_sha = sha256_path(tmp)
            have_sha = sha256_path(available) if available.exists() else None

            if have_sha == desired_sha:
                status = "up-to-date"
            else:
                status = "differs" if available.exists() else "not-installed"

            print(f"  src sha256: {desired_sha}")
            print(f"  dst sha256: {have_sha}")
            print(f"  status: {status}")
            if status == "differs":
                print("  diff:")
                print(diff_text(available, tmp))

            en = self._enabled_state(enabled)
            if en == "regular-file":
                print("  enabled: regular-file (should be symlink)")
            else:
                print(f"  enabled: {en}")

            print("  dry-run: no changes performed.")
            return 0
        finally:
            try:
                tmp.unlink()
            except FileNotFoundError:
                pass

    def apply(self, ctx: Context) -> int:
        fqdn = self._fqdn(ctx)
        available, enabled = self._paths(fqdn)

        rendered = self._render(fqdn)
        _sudo_install(available, rendered, mode="0644")

        if not enabled.is_symlink() and enabled.exists():
            _sudo_rm(enabled)
        _sudo_symlink(enabled, available)

        _run(["sudo", "nginx", "-t"])
        _run(["sudo", "systemctl", "reload", "nginx"])

        print("applied: nginx.8446.frontdoor")
        return 0


_REPO_ROOT = Path(__file__).resolve().parents[3]
ACTION = Nginx8446FrontdoorAction(template=_REPO_ROOT / "infra" / "nginx" / "8446-frontdoor.conf")
