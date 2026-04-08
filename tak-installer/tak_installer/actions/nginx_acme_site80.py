from __future__ import annotations

import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from takctl.config import load_config
from tak_installer.engine import Context
from tak_installer.util import sha256_path, diff_text
from tak_installer.runtime_state import get_fqdn


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def _sudo_write_file(dst: Path, content: str, mode: str = "0644") -> None:
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


def _sudo_symlink(link_path: Path, target: Path) -> None:
    _run(["sudo", "ln", "-sfn", str(target), str(link_path)])


def _sudo_rm(path: Path) -> None:
    _run(["sudo", "rm", "-f", str(path)])


def _cert_paths_for_fqdn(fqdn: str) -> tuple[Path, Path]:
    base = Path("/etc/letsencrypt/live") / fqdn
    return base / "fullchain.pem", base / "privkey.pem"


def _cert_exists(fqdn: str) -> bool:
    fullchain, privkey = _cert_paths_for_fqdn(fqdn)
    return fullchain.exists() and privkey.exists()


def _le_email() -> str:
    cfg = load_config()
    return str(cfg.get("le_email", "") or "").strip()


@dataclass(frozen=True)
class NginxAcme80Action:
    ID = "nginx.acme"

    template: Path
    dst_available: Path
    dst_enabled: Path

    def _fqdn(self, ctx: Context) -> str:
        return get_fqdn(ctx)

    def _render(self, fqdn: str) -> str:
        return self.template.read_text(encoding="utf-8").replace("__FQDN__", fqdn)

    def _enabled_state(self) -> str:
        if self.dst_enabled.is_symlink():
            try:
                return f"symlink -> {self.dst_enabled.resolve()}"
            except FileNotFoundError:
                return "symlink -> (broken)"
        if self.dst_enabled.exists():
            return "regular-file"
        return "missing"

    def inspect(self, ctx: Context) -> int:
        fqdn = self._fqdn(ctx)

        print("Nginx ACME site (port 80)")
        print(f"  template:   {self.template}")
        print(f"  available:  {self.dst_available}")
        print(f"  enabled:    {self.dst_enabled}")
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
            have_sha = sha256_path(self.dst_available) if self.dst_available.exists() else None

            if have_sha == desired_sha:
                status = "up-to-date"
            else:
                status = "differs" if self.dst_available.exists() else "not-installed"

            print(f"  src sha256: {desired_sha}")
            print(f"  dst sha256: {have_sha}")
            print(f"  status: {status}")
            if status == "differs":
                print("  diff:")
                print(diff_text(self.dst_available, tmp))

            en = self._enabled_state()
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
        rendered = self._render(fqdn)

        _sudo_write_file(self.dst_available, rendered, mode="0644")

        if not self.dst_enabled.is_symlink() and self.dst_enabled.exists():
            _sudo_rm(self.dst_enabled)

        _sudo_symlink(self.dst_enabled, self.dst_available)

        _run(["sudo", "nginx", "-t"])
        _run(["sudo", "systemctl", "reload", "nginx"])

        _run(["sudo", "install", "-d", "-o", "root", "-g", "root", "-m", "0755", "/var/www/letsencrypt"])
        _run(["sudo", "install", "-d", "-o", "root", "-g", "root", "-m", "0755", "/var/www/letsencrypt/.well-known"])
        _run(["sudo", "install", "-d", "-o", "root", "-g", "root", "-m", "0755", "/var/www/letsencrypt/.well-known/acme-challenge"])

        if _cert_exists(fqdn):
            print(f"nginx.acme: LE cert already present for {fqdn}")
        else:
            email = _le_email()
            cmd = [
                "sudo",
                "certbot",
                "certonly",
                "--non-interactive",
                "--agree-tos",
                "--webroot",
                "-w", "/var/www/letsencrypt",
                "-d", fqdn,
                "--keep-until-expiring",
            ]
            if email:
                cmd.extend(["--email", email])
            else:
                cmd.append("--register-unsafely-without-email")

            _run(cmd)

            if not _cert_exists(fqdn):
                raise RuntimeError(f"nginx.acme: certbot completed but cert files still missing for {fqdn}")

            print(f"nginx.acme: LE cert ready for {fqdn}")

        print("applied: nginx.acme")
        return 0


def _default_action(repo_root: Path) -> NginxAcme80Action:
    tmpl = repo_root / "infra" / "nginx" / "80-acme.conf"
    name = "80-acme-redirect"
    return NginxAcme80Action(
        template=tmpl,
        dst_available=Path("/etc/nginx/sites-available") / name,
        dst_enabled=Path("/etc/nginx/sites-enabled") / name,
    )


_REPO_ROOT = Path(__file__).resolve().parents[3]
ACTION = _default_action(_REPO_ROOT)
