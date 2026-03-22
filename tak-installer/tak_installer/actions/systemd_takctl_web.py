from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tak_installer.actions.systemd_unit import SystemdUnit
from tak_installer.engine import Context


UNIT_NAME = "takctl-web.service"
UNIT_DST = Path("/etc/systemd/system/takctl-web.service")
DROPIN_DST_DIR = Path("/etc/systemd/system/takctl-web.service.d")
STATE_APPLY_JSON = Path("/opt/tak/takctl-state/apply.json")

HEALTH_URL = "http://127.0.0.1:8080/api/health"

WAIT_LISTEN_SEC = 10.0
WAIT_HEALTH_SEC = 25.0
HEALTH_STABLE_SUCCESSES = 3
HEALTH_POLL_SEC = 0.25


def _unit_src(ctx: Context) -> Path:
    return Path(ctx.repo_root) / "infra" / "systemd" / "takctl-web.service"


def _dropin_src_dir(ctx: Context) -> Path:
    return Path(ctx.repo_root) / "infra" / "systemd" / "takctl-web.service.d"


def _run(cmd: list[str]) -> tuple[int, str]:
    try:
        p = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
        return int(p.returncode), (p.stdout or "").rstrip()
    except Exception as e:
        return 1, f"{type(e).__name__}: {e}"


def _read_apply_ts_from_state() -> str | None:
    try:
        raw = STATE_APPLY_JSON.read_text(encoding="utf-8").strip()
        if not raw:
            return None
        data = json.loads(raw)
        v = data.get("apply_ts_utc") if isinstance(data, dict) else None
        return str(v) if v else None
    except Exception:
        return None


def _http_get_json(url: str, timeout_sec: float = 1.5) -> tuple[int, Any, str | None]:
    req = urllib.request.Request(url, method="GET", headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=float(timeout_sec)) as r:
            code = int(getattr(r, "status", 200))
            raw = (r.read() or b"").decode("utf-8", "replace").strip()
            if not raw:
                return code, None, None
            try:
                return code, json.loads(raw), None
            except Exception:
                return code, raw, "non_json_response"
    except urllib.error.HTTPError as e:
        body = None
        try:
            body = (e.read() or b"").decode("utf-8", "replace").strip()
        except Exception:
            pass
        return int(e.code), {"error": str(e), "body": body}, "http_error"
    except Exception as e:
        return 0, {"error": repr(e)}, "exception"


def _wait_listen_8080(deadline_sec: float) -> bool:
    end = time.time() + float(deadline_sec)
    while time.time() < end:
        rc, out = _run(["ss", "-H", "-ltnp", "sport = :8080"])
        if rc == 0 and out.strip():
            return True
        time.sleep(0.10)
    return False


def _wait_health_stable(
    *,
    deadline_sec: float,
    expected_apply_ts: str | None,
    stable_successes: int = HEALTH_STABLE_SUCCESSES,
    poll_sec: float = HEALTH_POLL_SEC,
) -> tuple[bool, dict[str, Any] | None, dict[str, Any] | None]:
    end = time.time() + float(deadline_sec)
    streak = 0
    last_good: dict[str, Any] | None = None
    last_dict: dict[str, Any] | None = None

    while time.time() < end:
        code, body, _err = _http_get_json(HEALTH_URL, timeout_sec=1.5)

        if isinstance(body, dict):
            last_dict = body

        ok = (code == 200 and isinstance(body, dict))
        if ok and expected_apply_ts:
            got = body.get("apply_ts_utc") if isinstance(body, dict) else None
            ok = (got == expected_apply_ts)

        if ok:
            streak += 1
            last_good = body
            if streak >= int(stable_successes):
                return True, last_good, last_dict
        else:
            streak = 0

        time.sleep(float(poll_sec))

    return False, last_good, last_dict


def _sync_dropins(ctx: Context) -> None:
    src_dir = _dropin_src_dir(ctx)

    rc, out = _run(["sudo", "mkdir", "-p", str(DROPIN_DST_DIR)])
    if rc != 0:
        raise RuntimeError(out or "mkdir drop-in dir failed")

    rc, out = _run(["sudo", "bash", "-lc", f'rm -f "{DROPIN_DST_DIR}"/*.conf'])
    if rc != 0:
        raise RuntimeError(out or "remove old drop-ins failed")

    if src_dir.is_dir():
        for src in sorted(src_dir.glob("*.conf")):
            dst = DROPIN_DST_DIR / src.name
            rc, out = _run(["sudo", "install", "-m", "0644", str(src), str(dst)])
            if rc != 0:
                raise RuntimeError(out or f"install drop-in failed: {src.name}")

    rc, out = _run(["sudo", "systemctl", "daemon-reload"])
    if rc != 0:
        raise RuntimeError(out or "systemctl daemon-reload failed")


def _short_fail_dump() -> None:
    print("!! takctl-web not ready (or wrong apply token). Showing status + last logs:")
    rc, out = _run(["systemctl", "--no-pager", "--full", "status", UNIT_NAME])
    if out:
        print("\n".join(out.splitlines()[:60]))
    else:
        print(f"(systemctl status failed rc={rc})")

    print()
    rc, out = _run(["journalctl", "-u", UNIT_NAME, "--no-pager", "-n", "120"])
    print(out or f"(journalctl failed rc={rc})")


@dataclass(frozen=True)
class _Action:
    ID: str = "systemd.takctl-web"

    def inspect(self, ctx: Context) -> int:
        unit = SystemdUnit(
            name=UNIT_NAME,
            src=_unit_src(ctx),
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

        dropins = _dropin_src_dir(ctx)
        print(f"  dropin src dir: {dropins}")
        print(f"  dropin src exists: {str(dropins.is_dir()).lower()}")

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
            name=UNIT_NAME,
            src=_unit_src(ctx),
            dst=UNIT_DST,
        )

        info = unit.inspect()
        if info.get("status") == "missing-src":
            print(f"ERROR: source unit not found: {info.get('src')}")
            return 1

        expected_apply_ts = _read_apply_ts_from_state()

        if os.environ.get("TAKS_DEBUG", "") == "1":
            dbg = float(os.environ.get("TAKS_DEBUG_SLEEP_BEFORE_HEALTH", "0") or "0")
            if dbg > 0:
                print(f"debug: sleeping {dbg:.1f}s before health check")
                time.sleep(dbg)

        print(f"Applying systemd unit: {UNIT_NAME}")
        try:
            unit.apply()
            _sync_dropins(ctx)
        except PermissionError as e:
            print(f"ERROR: {e}")
            return 2
        except Exception as e:
            print(f"ERROR: action raised exception: {self.ID}: {e}")
            return 3

        rc, out = _run(["systemctl", "restart", UNIT_NAME])
        if rc != 0:
            print("ERROR: systemctl restart failed")
            print(out)
            return 4

        if not _wait_listen_8080(WAIT_LISTEN_SEC):
            _short_fail_dump()
            return 5

        ok, _last_good, _last_dict = _wait_health_stable(
            deadline_sec=WAIT_HEALTH_SEC,
            expected_apply_ts=expected_apply_ts,
        )
        if not ok:
            _short_fail_dump()
            return 5

        print("Applied.")
        if expected_apply_ts:
            print(f"takctl-web ready (apply_ts_utc={expected_apply_ts})")
        else:
            print("takctl-web ready")
        return 0


ACTION = _Action()
