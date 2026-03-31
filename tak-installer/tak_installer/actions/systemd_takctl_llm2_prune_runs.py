from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import shutil
import subprocess

from tak_installer.actions.systemd_unit import SystemdUnit
from tak_installer.engine import Context


SERVICE_NAME = "takctl-llm2-prune-runs.service"
TIMER_NAME = "takctl-llm2-prune-runs.timer"

SERVICE_DST = Path("/etc/systemd/system") / SERVICE_NAME
TIMER_DST = Path("/etc/systemd/system") / TIMER_NAME

SCRIPT_NAME = "takctl-llm2-prune-runs"
SCRIPT_DST = Path("/opt/tak/tools/takctl/bin") / SCRIPT_NAME


def _run(argv: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(argv, check=check, text=True, capture_output=False)


def _installer_root(ctx: Context) -> Path:
    p = Path(ctx.repo_root)
    if (p / "tak_installer").is_dir() and (p / "infra").is_dir():
        return p
    if (p / "tak-installer" / "tak_installer").is_dir() and (p / "tak-installer" / "infra").is_dir():
        return p / "tak-installer"
    raise RuntimeError(f"could not resolve tak-installer repo root from: {p}")


@dataclass(frozen=True)
class _Action:
    ID: str = "systemd.takctl-llm2-prune-runs"

    def inspect(self, ctx: Context) -> int:
        root = _installer_root(ctx)

        script_src = root / "infra" / "bin" / SCRIPT_NAME
        service_src = root / "infra" / "systemd" / SERVICE_NAME
        timer_src = root / "infra" / "systemd" / TIMER_NAME

        print(f"Installer root: {root}")
        print(f"Script source:  {script_src}")
        print(f"Script dest:    {SCRIPT_DST}")
        print(f"Service src:    {service_src}")
        print(f"Service dst:    {SERVICE_DST}")
        print(f"Timer src:      {timer_src}")
        print(f"Timer dst:      {TIMER_DST}")

        service_unit = SystemdUnit(name=SERVICE_NAME, src=service_src, dst=SERVICE_DST)
        timer_unit = SystemdUnit(name=TIMER_NAME, src=timer_src, dst=TIMER_DST)

        sinfo = service_unit.inspect()
        tinfo = timer_unit.inspect()

        if not script_src.exists():
            print(f"ERROR: source script not found: {script_src}")
            return 1
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
        root = _installer_root(ctx)

        script_src = root / "infra" / "bin" / SCRIPT_NAME
        service_src = root / "infra" / "systemd" / SERVICE_NAME
        timer_src = root / "infra" / "systemd" / TIMER_NAME

        if not script_src.exists():
            raise RuntimeError(f"missing script source: {script_src}")
        if not service_src.exists():
            raise RuntimeError(f"missing service source: {service_src}")
        if not timer_src.exists():
            raise RuntimeError(f"missing timer source: {timer_src}")

        SCRIPT_DST.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(script_src, SCRIPT_DST)
        os.chmod(SCRIPT_DST, 0o755)

        try:
            shutil.chown(SCRIPT_DST, user="tak", group="tak")
        except Exception:
            _run(["sudo", "chown", "tak:tak", str(SCRIPT_DST)])

        service_unit = SystemdUnit(name=SERVICE_NAME, src=service_src, dst=SERVICE_DST)
        timer_unit = SystemdUnit(name=TIMER_NAME, src=timer_src, dst=TIMER_DST)

        print(f"Applying systemd unit: {SERVICE_NAME}")
        service_unit.apply()

        print(f"Applying systemd unit: {TIMER_NAME}")
        timer_unit.apply()

        _run(["sudo", "systemctl", "daemon-reload"])
        _run(["sudo", "systemctl", "enable", "--now", TIMER_NAME])

        return 0


ACTION = _Action()
