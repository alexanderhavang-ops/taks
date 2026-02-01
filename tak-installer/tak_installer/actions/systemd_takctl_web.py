from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tak_installer.engine import Context
from tak_installer.actions.systemd_unit import SystemdUnit


@dataclass(frozen=True)
class _Action:
    ID: str = "systemd.takctl-web"

    def inspect(self, ctx: Context) -> int:
        unit = SystemdUnit(
            name="takctl-web.service",
            src=ctx.repo_root / "infra" / "systemd" / "takctl-web.service",
            dst=Path("/etc/systemd/system/takctl-web.service"),
        )

        info = unit.inspect()
        if info.get("status") == "missing-src":
            print(f"ERROR: source unit not found: {info.get('src')}")
            return 1

        print("Systemd unit: takctl-web.service")
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

        print("  dry-run: no changes performed.")
        return 0

    def apply(self, ctx: Context) -> int:
        unit = SystemdUnit(
            name="takctl-web.service",
            src=ctx.repo_root / "infra" / "systemd" / "takctl-web.service",
            dst=Path("/etc/systemd/system/takctl-web.service"),
        )

        info = unit.inspect()
        if info.get("status") == "missing-src":
            print(f"ERROR: source unit not found: {info.get('src')}")
            return 1

        print("Applying systemd unit: takctl-web.service")
        try:
            unit.apply()
        except PermissionError as e:
            print(f"ERROR: {e}")
            return 2

        print("Applied.")
        return 0


ACTION = _Action()
