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


def _sudo_write(dst: Path, content: str, mode: str = "0644") -> None:
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
class Nginx443TakctlAction:
    ID = "nginx.443.takctl"

    dst_available: Path
    dst_enabled: Path

    def _fqdn(self, ctx: Context) -> str:
        fqdn = ctx.env.get("FQDN") or ctx.env.get("TAKS_FQDN") or ""
        if not fqdn:
            raise RuntimeError("FQDN not set. Provide FQDN env var (or TAKS_FQDN).")
        return fqdn.strip()

    def _render(self, fqdn: str) -> str:
        # Deterministic vhost: only /takctl/, deny everything else.
        fullchain = f"/etc/letsencrypt/live/{fqdn}/fullchain.pem"
        privkey = f"/etc/letsencrypt/live/{fqdn}/privkey.pem"
        return f"""server {{
    listen 443 ssl;
    server_name {fqdn};

    # TLS
    ssl_certificate     {fullchain};
    ssl_certificate_key {privkey};

    include /etc/nginx/snippets/ssl-common.conf;
    include /etc/nginx/snippets/deny-dotfiles.conf;

    # ------------------------------------------------------------
    # takctl-web (FastAPI + static UI)
    # URL: https://{fqdn}/takctl/
    # Backend: http://127.0.0.1:8080/
    # ------------------------------------------------------------

    location = /takctl {{
        return 301 /takctl/;
    }}

    location /takctl/ {{
        proxy_http_version 1.1;

        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Trailing slash is IMPORTANT
        proxy_pass http://127.0.0.1:8080/;

        proxy_read_timeout  60s;
        proxy_send_timeout  60s;
    }}

    # Explicitly deny everything else
    location / {{
        return 404;
    }}
}}
"""

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

        print("Nginx 443 site (takctl only)")
        print(f"  available:  {self.dst_available}")
        print(f"  enabled:    {self.dst_enabled}")
        print(f"  fqdn:       {fqdn}")

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

        _sudo_write(self.dst_available, rendered, mode="0644")

        # normalize enabled -> symlink
        if not self.dst_enabled.is_symlink() and self.dst_enabled.exists():
            _sudo_rm(self.dst_enabled)
        _sudo_symlink(self.dst_enabled, self.dst_available)

        _run(["sudo", "nginx", "-t"])
        _run(["sudo", "systemctl", "reload", "nginx"])

        print("applied: nginx.443.takctl")
        return 0


def _default_action() -> Nginx443TakctlAction:
    # Derive filename from FQDN at runtime; but we still need fixed paths here,
    # so we keep a placeholder name and compute real paths inside inspect/apply.
    # Instead: keep stable naming convention and build paths in inspect/apply.
    # We'll implement that by hardcoding to tak-<fqdn>-443.conf via ctx.fqdn.
    # But ACTION must be an object. So we store dummy paths and override per-run.
    return Nginx443TakctlAction(
        dst_available=Path("/etc/nginx/sites-available/__FQDN__-443.conf"),
        dst_enabled=Path("/etc/nginx/sites-enabled/__FQDN__-443.conf"),
    )


class _Wrapper:
    ID = "nginx.443.takctl"

    def inspect(self, ctx: Context) -> int:
        fqdn = (ctx.env.get("FQDN") or ctx.env.get("TAKS_FQDN") or "").strip()
        if not fqdn:
            raise RuntimeError("FQDN not set. Provide FQDN env var (or TAKS_FQDN).")
        a = Nginx443TakctlAction(
            dst_available=Path("/etc/nginx/sites-available") / f"tak-{fqdn}-443.conf",
            dst_enabled=Path("/etc/nginx/sites-enabled") / f"tak-{fqdn}-443.conf",
        )
        return a.inspect(ctx)

    def apply(self, ctx: Context) -> int:
        fqdn = (ctx.env.get("FQDN") or ctx.env.get("TAKS_FQDN") or "").strip()
        if not fqdn:
            raise RuntimeError("FQDN not set. Provide FQDN env var (or TAKS_FQDN).")
        a = Nginx443TakctlAction(
            dst_available=Path("/etc/nginx/sites-available") / f"tak-{fqdn}-443.conf",
            dst_enabled=Path("/etc/nginx/sites-enabled") / f"tak-{fqdn}-443.conf",
        )
        return a.apply(ctx)


ACTION = _Wrapper()
