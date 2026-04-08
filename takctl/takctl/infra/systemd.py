from __future__ import annotations

from dataclasses import dataclass
import subprocess

from takctl.config import RuntimeConfig


@dataclass
class Systemd:
    cfg: RuntimeConfig

    def is_active(self) -> bool:
        try:
            subprocess.check_call(["systemctl", "is-active", "--quiet", self.cfg.tak_service])
            return True
        except Exception:
            return False

    def restart(self) -> None:
        subprocess.check_call(["sudo", "systemctl", "restart", self.cfg.tak_service])

    def active_enter_timestamp(self) -> str:
        out = subprocess.check_output(
            ["systemctl", "show", self.cfg.tak_service, "-p", "ActiveEnterTimestamp"],
            text=True,
        )
        return out.strip().split("=", 1)[1] if "=" in out else out.strip()
