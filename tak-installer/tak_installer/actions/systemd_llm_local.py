from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tak_installer.engine import Context
from tak_installer.actions.systemd_unit import SystemdUnit


@dataclass(frozen=True)
class _Action:
    ID: str = "systemd.llm-local"

    def inspect(self, ctx: Context) -> int:
        unit = SystemdUnit(
            name="llm-local.service",
            src=ctx.repo_root / "llm-infra" / "systemd" / "llm-local.service",
            dst=Path("/etc/systemd/system/llm-local.service"),
        )

        info = unit.inspect()
        if info.get("status") == "missing-src":
            print(f"ERROR: source unit not found: {info.get('src')}")
            return 1

        print("Systemd unit: llm-local.service")
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

        payload_present = Path("/opt/llm").exists()
        print(f"  payload: {'present' if payload_present else 'missing'}")
        print("  apply behavior: install unit + daemon-reload; restart only if payload present")
        print("  dry-run: no changes performed.")
        return 0

    def apply(self, ctx: Context) -> int:
        unit = SystemdUnit(
            name="llm-local.service",
            src=ctx.repo_root / "llm-infra" / "systemd" / "llm-local.service",
            dst=Path("/etc/systemd/system/llm-local.service"),
        )

        info = unit.inspect()
        if info.get("status") == "missing-src":
            print(f"ERROR: source unit not found: {info.get('src')}")
            return 1

        print("Applying systemd unit: llm-local.service")
        try:
            # Install unit + daemon-reload (+ conditional restart) performed by SystemdUnit.apply()
            # We want to avoid restart loops on nodes without /opt/llm, so we only restart when payload exists.
            payload_present = Path("/opt/llm").exists()
            if payload_present:
                unit.apply()
                print("Applied (payload present → restarted if changed).")
            else:
                # Temporarily neutralize restart-on-change behavior by pointing to a dummy name? No.
                # Instead: do a no-restart apply path by copying content via SystemdUnit, then daemon-reload, but skip restart.
                # We implement that by calling unit.apply() only when payload exists.
                #
                # When payload is missing, we still want the unit file to be installed/updated.
                # So we reproduce SystemdUnit.apply() without the restart step:
                from tak_installer.actions.systemd_unit import _run, _sudo_install  # type: ignore
                import os
                import tempfile

                if not unit.src.is_file():
                    raise FileNotFoundError(f"source unit not found: {unit.src}")

                src_text = unit.src.read_text(encoding="utf-8")

                # Ensure parent exists (privileged path)
                _run(["sudo", "mkdir", "-p", str(unit.dst.parent)], check=True)

                # Write temp file in /tmp then sudo install into /etc
                with tempfile.NamedTemporaryFile("w", delete=False, suffix=".tmp") as tf:
                    tf.write(src_text)
                    tmp = tf.name
                try:
                    _run(["sudo", "install", "-m", "0644", tmp, str(unit.dst)], check=True)
                finally:
                    try:
                        os.unlink(tmp)
                    except FileNotFoundError:
                        pass

                _run(["sudo", "systemctl", "daemon-reload"], check=True)
                _run(["sudo", "systemctl", "disable", "--now", "llm-local.service"], check=False)
                print("Applied (payload missing → disabled, no restart).")

        except PermissionError as e:
            print(f"ERROR: {e}")
            return 2

        return 0


ACTION = _Action()

