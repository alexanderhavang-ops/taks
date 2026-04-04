from __future__ import annotations

import subprocess
from pathlib import Path

from tak_installer.runtime_state import get_fqdn


class Nginx8446FrontdoorAction:
    ID = "nginx.8446.frontdoor"

    def inspect(self, ctx) -> int:
        fqdn = get_fqdn(ctx)
        print("Nginx 8446 frontdoor: passive/disabled (TAK server owns 8446 directly)")
        print(f"fqdn: {fqdn}")
        print("action: would remove legacy nginx 8446 site files if present")
        return 0

    def apply(self, ctx) -> int:
        fqdn = get_fqdn(ctx)

        candidates = [
            Path("/etc/nginx/sites-enabled/tak-enroll-8446"),
            Path("/etc/nginx/sites-available/tak-enroll-8446"),
            Path(f"/etc/nginx/sites-enabled/tak-{fqdn}-enroll-8446.conf"),
            Path(f"/etc/nginx/sites-available/tak-{fqdn}-enroll-8446.conf"),
        ]

        changed = False
        for c in candidates:
            if c.exists() or c.is_symlink():
                subprocess.run(["sudo", "rm", "-f", str(c)], check=False)
                changed = True

        print(f"applied: nginx.8446.frontdoor passive (removed_legacy={str(changed).lower()})")
        return 0


ACTION = Nginx8446FrontdoorAction()
