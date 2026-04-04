from __future__ import annotations

import subprocess
from pathlib import Path


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


class Nginx8446FrontdoorAction:
    ID = "nginx.8446.frontdoor"

    def inspect(self, ctx) -> int:
        print("Nginx 8446 frontdoor: disabled (TAK server owns 8446 directly)")
        return 0

    def apply(self, ctx) -> int:
        fqdn = ctx.get("fqdn") if isinstance(getattr(ctx, "__class__", None), type) else None
        try:
            from tak_installer.runtime_state import get_fqdn
            fqdn = get_fqdn(ctx)
        except Exception:
            fqdn = None

        candidates = [
            Path("/etc/nginx/sites-enabled/tak-enroll-8446"),
            Path("/etc/nginx/sites-available/tak-enroll-8446"),
        ]
        if fqdn:
            candidates.extend([
                Path(f"/etc/nginx/sites-enabled/tak-{fqdn}-enroll-8446.conf"),
                Path(f"/etc/nginx/sites-available/tak-{fqdn}-enroll-8446.conf"),
            ])

        for c in candidates:
            subprocess.run(["sudo", "rm", "-f", str(c)], check=False)

        _run(["sudo", "nginx", "-t"])
        _run(["sudo", "systemctl", "reload", "nginx"])
        print("applied: nginx.8446.frontdoor disabled/removed")
        return 0


ACTION = Nginx8446FrontdoorAction()
