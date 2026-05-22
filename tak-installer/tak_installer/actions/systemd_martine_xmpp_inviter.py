from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess

from tak_installer.actions.systemd_unit import SystemdUnit
from tak_installer.engine import Context


UNIT_NAME = "martine-xmpp-inviter.service"
UNIT_DST = Path("/etc/systemd/system/martine-xmpp-inviter.service")


def _truthy(value: object, default: bool = False) -> bool:
    if value is None:
        return default
    s = str(value).strip().lower()
    if not s:
        return default
    return s in ("1", "true", "yes", "y", "on", "enabled")


def _openfire_enabled(ctx: Context) -> bool:
    env = dict(ctx.env or {})
    return _truthy(
        env.get("openfire_enabled", env.get("OPENFIRE_ENABLED", "true")),
        default=True,
    )


@dataclass(frozen=True)
class _Action:
    ID: str = "systemd.martine-xmpp-inviter"

    def inspect(self, ctx: Context) -> int:
        enabled = _openfire_enabled(ctx)

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
        print(f"  openfire_enabled: {str(enabled).lower()}")
        print(f"  src: {info['src']}")
        print(f"  dst: {info['dst']}")
        print(f"  src sha256: {info['src_sha256']}")
        if not enabled:
            print("  status: skipped because openfire_enabled != true")
            return 0

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
        if not _openfire_enabled(ctx):
            print("applied: martine-xmpp-inviter skipped (openfire_enabled != true)")
            return 0

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
