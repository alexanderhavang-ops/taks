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
DROPIN_SRC_DIR = Path("/opt/taks/infra/systemd/takctl-web.service.d")
DROPIN_DST_DIR = Path("/etc/systemd/system/takctl-web.service.d")
STATE_APPLY_JSON = Path("/opt/tak/takctl-state/apply.json")

HEALTH_URL = "http://127.0.0.1:8080/api/health"

# Conservative waits: restart + uvicorn import time + startup flaps.
WAIT_LISTEN_SEC = 10.0
WAIT_HEALTH_SEC = 25.0

# Readiness stability requirement: must pass health N times in a row.
HEALTH_STABLE_SUCCESSES = 3
HEALTH_POLL_SEC = 0.25


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
    # Avoid races after restart. Query only :8080 to avoid false positives.
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
    """
    Wait for /api/health to be stable:
      - must return 200 + JSON dict
      - if expected_apply_ts is present, must match apply_ts_utc
      - must succeed N times consecutively (to avoid transient flaps)
    Returns: (ok, last_good_health, last_dict_body)
      - last_good_health: dict from the most recent streak success
      - last_dict_body: best-effort last dict-shaped body (for diagnostics)
    """
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
            last_good = body  # type: ignore[assignment]
            if streak >= int(stable_successes):
                return True, last_good, last_dict
        else:
            streak = 0

        time.sleep(float(poll_sec))

    return False, last_good, last_dict



def _sync_dropins() -> None:
    """
    Install/refresh systemd drop-ins for takctl-web from the repo.
    This is installer-owned and deterministic.
    """
    if not DROPIN_SRC_DIR.is_dir():
        return

    # Ensure dst dir exists
    rc, out = _run(["sudo", "mkdir", "-p", str(DROPIN_DST_DIR)])
    if rc != 0:
        raise RuntimeError(out or "mkdir drop-in dir failed")

    # Copy *.conf files
    for src in sorted(DROPIN_SRC_DIR.glob("*.conf")):
        dst = DROPIN_DST_DIR / src.name
        rc, out = _run(["sudo", "install", "-m", "0644", str(src), str(dst)])
        if rc != 0:
            raise RuntimeError(out or f"install drop-in failed: {src.name}")

    rc, out = _run(["sudo", "systemctl", "daemon-reload"])
    if rc != 0:
        raise RuntimeError(out or "systemctl daemon-reload failed")



    # Ensure dst dir exists
    _run(["sudo", "mkdir", "-p", str(DROPIN_DST_DIR)])

    # Copy *.conf files
    for src in sorted(DROPIN_SRC_DIR.glob("*.conf")):
        dst = DROPIN_DST_DIR / src.name
        # sudo install preserves mode deterministically
        _run(["sudo", "install", "-m", "0644", str(src), str(dst)])

    _run(["sudo", "systemctl", "daemon-reload"])


def _short_fail_dump() -> None:
    print("!! takctl-web not ready (or wrong apply token). Showing status + last logs:")
    rc, out = _run(["systemctl", "--no-pager", "--full", "status", UNIT_NAME])
    if out:
        print(out.splitlines()[0] if out else "")
        # keep it short
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
            src=ctx.repo_root / "infra" / "systemd" / "takctl-web.service",
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

        print("  dry-run: no changes performed.")
        return 0

    def apply(self, ctx: Context) -> int:
        unit = SystemdUnit(
            name=UNIT_NAME,
            src=ctx.repo_root / "infra" / "systemd" / "takctl-web.service",
            dst=UNIT_DST,
        )

        info = unit.inspect()
        if info.get("status") == "missing-src":
            print(f"ERROR: source unit not found: {info.get('src')}")
            return 1

        expected_apply_ts = _read_apply_ts_from_state()

        # DEBUG: allow deterministic mismatch testing (must opt-in)
        if os.environ.get("TAKS_DEBUG", "") == "1":
            dbg = float(os.environ.get("TAKS_DEBUG_SLEEP_BEFORE_HEALTH", "0") or "0")
            if dbg > 0:
                print(f"debug: sleeping {dbg:.1f}s before health check")
                time.sleep(dbg)

        print(f"Applying systemd unit: {UNIT_NAME}")
        try:
            unit.apply()
        except PermissionError as e:
            print(f"ERROR: {e}")
            return 2

        _sync_dropins()

        # Always restart to pick up new runtime code / venv state deterministically.
        rc, out = _run(["systemctl", "restart", UNIT_NAME])
        if rc != 0:
            print("ERROR: systemctl restart failed")
            print(out)
            return 3

        # Wait for LISTEN (avoid immediate curl race)
        if not _wait_listen_8080(WAIT_LISTEN_SEC):
            _short_fail_dump()
            return 4

        # Wait for /api/health to be STABLE (avoid transient up/down or apply_ts lag)
        ok, last_good, last_dict = _wait_health_stable(
            deadline_sec=WAIT_HEALTH_SEC,
            expected_apply_ts=expected_apply_ts,
            stable_successes=HEALTH_STABLE_SUCCESSES,
            poll_sec=HEALTH_POLL_SEC,
        )
        if not ok or not isinstance(last_good, dict):
            # If we have a dict-ish response, print the key reason plainly.
            if expected_apply_ts and isinstance(last_dict, dict):
                got_apply_ts = last_dict.get("apply_ts_utc")
                if got_apply_ts and got_apply_ts != expected_apply_ts:
                    print("ERROR: takctl-web served a different apply token than installer state.")
                    print(f"  expected apply_ts_utc: {expected_apply_ts}")
                    print(f"  got apply_ts_utc:      {got_apply_ts}")
            _short_fail_dump()
            return 5

        print("Applied.")
        if expected_apply_ts:
            print(f"takctl-web ready (apply_ts_utc={expected_apply_ts})")
        else:
            print("takctl-web ready (no apply_ts_utc in state yet)")
        return 0


ACTION = _Action()
