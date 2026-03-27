from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tak_installer.actions.systemd_unit import SystemdUnit, _run
from tak_installer.engine import Context


SERVICE_NAME = "takctl-weather-refresh.service"
TIMER_NAME = "takctl-weather-refresh.timer"

SERVICE_DST = Path("/etc/systemd/system") / SERVICE_NAME
TIMER_DST = Path("/etc/systemd/system") / TIMER_NAME


@dataclass(frozen=True)
class _Action:
    ID: str = "systemd.takctl-weather-refresh"

    def inspect(self, ctx: Context) -> int:
        service_src = ctx.repo_root / "infra" / "systemd" / SERVICE_NAME
        timer_src = ctx.repo_root / "infra" / "systemd" / TIMER_NAME

        service_unit = SystemdUnit(
            name=SERVICE_NAME,
            src=service_src,
            dst=SERVICE_DST,
        )
        timer_unit = SystemdUnit(
            name=TIMER_NAME,
            src=timer_src,
            dst=TIMER_DST,
        )

        sinfo = service_unit.inspect()
        tinfo = timer_unit.inspect()

        if sinfo.get("status") == "missing-src":
            print(f"ERROR: source unit not found: {sinfo.get('src')}")
            return 1
        if tinfo.get("status") == "missing-src":
            print(f"ERROR: source unit not found: {tinfo.get('src')}")
            return 1

        print(f"Systemd unit: {SERVICE_NAME}")
        print(f"  src: {sinfo['src']}")
        print(f"  dst: {sinfo['dst']}")
        print(f"  src sha256: {sinfo['src_sha256']}")
        if sinfo["status"] == "not-installed":
            print("  status: not installed")
        else:
            print(f"  dst sha256: {sinfo['dst_sha256']}")
            print(f"  status: {sinfo['status']}")
            if sinfo["status"] == "differs":
                print("  diff:")
                print(sinfo.get("diff") or "(no diff output)")

        print()

        print(f"Systemd unit: {TIMER_NAME}")
        print(f"  src: {tinfo['src']}")
        print(f"  dst: {tinfo['dst']}")
        print(f"  src sha256: {tinfo['src_sha256']}")
        if tinfo["status"] == "not-installed":
            print("  status: not installed")
        else:
            print(f"  dst sha256: {tinfo['dst_sha256']}")
            print(f"  status: {tinfo['status']}")
            if tinfo["status"] == "differs":
                print("  diff:")
                print(tinfo.get("diff") or "(no diff output)")
        return 0

    def apply(self, ctx: Context) -> int:
        service_src = ctx.repo_root / "infra" / "systemd" / SERVICE_NAME
        timer_src = ctx.repo_root / "infra" / "systemd" / TIMER_NAME

        service_unit = SystemdUnit(
            name=SERVICE_NAME,
            src=service_src,
            dst=SERVICE_DST,
        )
        timer_unit = SystemdUnit(
            name=TIMER_NAME,
            src=timer_src,
            dst=TIMER_DST,
        )

        sinfo = service_unit.inspect()
        tinfo = timer_unit.inspect()

        if sinfo.get("status") == "missing-src":
            print(f"ERROR: source unit not found: {sinfo.get('src')}")
            return 1
        if tinfo.get("status") == "missing-src":
            print(f"ERROR: source unit not found: {tinfo.get('src')}")
            return 1

        print(f"Applying systemd unit: {SERVICE_NAME}")
        try:
            service_unit.apply()
        except PermissionError as e:
            print(f"ERROR: {e}")
            return 2

        print(f"Applying systemd unit: {TIMER_NAME}")
        try:
            timer_unit.apply()
        except PermissionError as e:
            print(f"ERROR: {e}")
            return 2

        rc, out = _run(["sudo", "systemctl", "daemon-reload"])
        if rc != 0:
            raise RuntimeError(out or "systemctl daemon-reload failed")

        rc, out = _run(["sudo", "systemctl", "enable", TIMER_NAME])
        if rc != 0:
            raise RuntimeError(out or f"systemctl enable failed: {TIMER_NAME}")

        rc, out = _run(["sudo", "systemctl", "restart", TIMER_NAME])
        if rc != 0:
            raise RuntimeError(out or f"systemctl restart failed: {TIMER_NAME}")

        return 0


ACTION = _Action()
