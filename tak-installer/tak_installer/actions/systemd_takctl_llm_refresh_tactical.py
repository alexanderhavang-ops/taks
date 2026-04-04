from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess

from takctl.config import load_config as load_takctl_config


SERVICE_NAME = "takctl-llm-refresh-tactical.service"
TIMER_NAME = "takctl-llm-refresh-tactical.timer"

SERVICE_DST = Path("/etc/systemd/system") / SERVICE_NAME
TIMER_DST = Path("/etc/systemd/system") / TIMER_NAME


def _run(argv: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(argv, check=check, text=True, capture_output=False)


def _refresh_interval_hours() -> int:
    try:
        cfg = load_takctl_config()
        raw = str(cfg.get("llm3_refresh_interval_hours", "1") or "1").strip()
        return max(0, int(raw))
    except Exception:
        return 1


def _service_text() -> str:
    return """[Unit]
Description=TAKCTL LLM3 refresh tactical state
After=network-online.target
Wants=network-online.target

[Service]
EnvironmentFile=/opt/tak/tools/takctl/secrets/db.env
Type=oneshot
User=tak
Group=tak
WorkingDirectory=/opt/tak/tools/takctl
ExecStart=/bin/bash -lc '/opt/tak/tools/takctl/scripts/runllmphase3.sh phase2 all && /opt/tak/tools/takctl/scripts/runllmphase3.sh phase3 all'
"""


def _timer_text(hours: int) -> str:
    return f"""[Unit]
Description=Run TAKCTL LLM3 refresh (tactical operations)

[Timer]
OnBootSec=2min
OnUnitActiveSec={hours}h
Persistent=true
Unit={SERVICE_NAME}

[Install]
WantedBy=timers.target
"""


def _write_root_file(path: Path, text: str) -> None:
    tmp = Path("/tmp") / (path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    _run(["sudo", "install", "-o", "root", "-g", "root", "-m", "0644", str(tmp), str(path)])
    try:
        tmp.unlink()
    except Exception:
        pass


@dataclass(frozen=True)
class _Action:
    ID: str = "systemd.takctl-llm-refresh-tactical"

    def inspect(self, ctx) -> int:
        hours = _refresh_interval_hours()
        print(f"Service dst: {SERVICE_DST}")
        print(f"Timer dst:   {TIMER_DST}")
        print(f"llm3_refresh_interval_hours = {hours}")
        print("timer_enabled = " + ("yes" if hours > 0 else "no"))
        return 0

    def apply(self, ctx) -> int:
        hours = _refresh_interval_hours()

        _write_root_file(SERVICE_DST, _service_text())
        _write_root_file(TIMER_DST, _timer_text(max(1, hours if hours > 0 else 1)))

        _run(["sudo", "systemctl", "daemon-reload"])

        if hours <= 0:
            _run(["sudo", "systemctl", "disable", "--now", TIMER_NAME], check=False)
        else:
            _run(["sudo", "systemctl", "enable", "--now", TIMER_NAME])

        return 0


ACTION = _Action()
