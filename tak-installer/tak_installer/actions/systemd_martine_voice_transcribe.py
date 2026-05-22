from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess

from tak_installer.actions.systemd_unit import SystemdUnit
from tak_installer.engine import Context


UNIT_NAME = "martine-voice-transcribe.service"
UNIT_DST = Path("/etc/systemd/system/martine-voice-transcribe.service")


@dataclass(frozen=True)
class _Action:
    ID: str = "systemd.martine-voice-transcribe"

    def inspect(self, ctx: Context) -> int:
        unit = SystemdUnit(
            name=UNIT_NAME,
            src=ctx.repo_root / "infra" / "systemd" / UNIT_NAME,
            dst=UNIT_DST,
        )
        info = unit.inspect()
        if info.get("status") == "missing-src":
            print(f"ERROR: source unit not found: {info.get('src')}")
            return 1

        print(f"Systemd unit: {UNIT_NAME}")
        print(f"  src: {info['src']}")
        print(f"  dst: {info['dst']}")
        print(f"  src sha256: {info['src_sha256']}")
        if info["status"] == "not-installed":
            print("  status: not installed")
        else:
            print(f"  dst sha256: {info['dst_sha256']}")
            print(f"  status: {info['status']}")
            if info["status"] == "differs":
                print("  diff:")
                print(info.get("diff") or "(no diff output)")
        return 0

    def apply(self, ctx: Context) -> int:
        unit = SystemdUnit(
            name=UNIT_NAME,
            src=ctx.repo_root / "infra" / "systemd" / UNIT_NAME,
            dst=UNIT_DST,
        )

        info = unit.inspect()
        if info.get("status") == "missing-src":
            print(f"ERROR: source unit not found: {info.get('src')}")
            return 1

        print(f"Applying systemd unit: {UNIT_NAME}")
        try:
            unit.apply()
        except PermissionError as e:
            print(f"ERROR: {e}")
            return 2

        subprocess.run(["sudo", "systemctl", "enable", "--now", UNIT_NAME], check=False)
        print(f"applied: {UNIT_NAME} enabled and started")
        return 0


ACTION = _Action()
