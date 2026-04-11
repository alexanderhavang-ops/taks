from __future__ import annotations

import json
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
WANTS_LINK = Path("/etc/systemd/system/multi-user.target.wants") / UNIT_NAME
STATE_APPLY_JSON = Path("/opt/tak/takctl-state/apply.json")
STATE_VERIFY_JSON = Path("/opt/tak/takctl-state/systemd-takctl-web.json")

HEALTH_URL = "http://127.0.0.1:8080/api/health"

WAIT_LISTEN_SEC = 10.0
WAIT_HEALTH_SEC = 25.0
HEALTH_STABLE_SUCCESSES = 3
HEALTH_POLL_SEC = 0.25


def _repo_root(ctx: Context) -> Path:
    return Path(ctx.repo_root)


def _unit_src(ctx: Context) -> Path:
    root = _repo_root(ctx)
    candidates = [
        root / "infra" / "systemd" / "takctl-web.service",
        root / "tak-installer" / "infra" / "systemd" / "takctl-web.service",
    ]
    for p in candidates:
        if p.exists():
            return p
    return candidates[0]


def _dropin_src_dir(ctx: Context) -> Path:
    root = _repo_root(ctx)
    candidates = [
        root / "infra" / "systemd" / "takctl-web.service.d",
        root / "tak-installer" / "infra" / "systemd" / "takctl-web.service.d",
    ]
    for p in candidates:
        if p.exists():
            return p
    return candidates[0]


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


def _unit_show_map() -> dict[str, str]:
    rc, out = _run([
        "systemctl", "show", UNIT_NAME,
        "-p", "UnitFileState",
        "-p", "LoadState",
        "-p", "ActiveState",
        "-p", "SubState",
        "-p", "FragmentPath",
        "-p", "UnitFilePreset",
    ])
    data: dict[str, str] = {}
    for line in (out or "").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            data[k] = v
    if rc != 0 and not data:
        data["show_error"] = out or f"rc={rc}"
    return data


def _collect_runtime_state() -> dict[str, Any]:
    rc_enabled, out_enabled = _run(["systemctl", "is-enabled", UNIT_NAME])
    rc_active, out_active = _run(["systemctl", "is-active", UNIT_NAME])
    rc_ss, out_ss = _run(["ss", "-H", "-ltnp", "sport = :8080"])
    return {
        "show": _unit_show_map(),
        "is_enabled_rc": rc_enabled,
        "is_enabled": (out_enabled or "").strip(),
        "is_active_rc": rc_active,
        "is_active": (out_active or "").strip(),
        "wants_symlink_exists": WANTS_LINK.exists(),
        "wants_symlink": str(WANTS_LINK),
        "listen_8080_rc": rc_ss,
        "listen_8080": bool((out_ss or "").strip()),
        "listen_8080_out": out_ss,
    }


def _write_verify_state(payload: dict[str, Any]) -> None:
    try:
        STATE_VERIFY_JSON.parent.mkdir(parents=True, exist_ok=True)
        tmp = STATE_VERIFY_JSON.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(STATE_VERIFY_JSON)
    except Exception as e:
        print(f"WARN: could not write verify state: {type(e).__name__}: {e}")


def _ensure_enabled_and_started() -> tuple[int, str]:
    commands = [
        ["sudo", "systemctl", "daemon-reload"],
        ["sudo", "systemctl", "reenable", UNIT_NAME],
        ["sudo", "systemctl", "enable", UNIT_NAME],
        ["sudo", "systemctl", "restart", UNIT_NAME],
    ]
    outs: list[str] = []
    for cmd in commands:
        rc, out = _run(cmd)
        outs.append("$ " + " ".join(cmd))
        if out:
            outs.append(out)
        if rc != 0:
            return rc, "\n".join(outs)
    return 0, "\n".join(outs)


def _short_fail_dump() -> dict[str, Any]:
    print("!! takctl-web not ready (or wrong apply token). Showing status + last logs:")
    rc_status, out_status = _run(["systemctl", "--no-pager", "--full", "status", UNIT_NAME])
    if out_status:
        print("\n".join(out_status.splitlines()[:80]))
    else:
        print(f"(systemctl status failed rc={rc_status})")

    print()
    rc_journal, out_journal = _run(["journalctl", "-u", UNIT_NAME, "--no-pager", "-n", "120"])
    print(out_journal or f"(journalctl failed rc={rc_journal})")

    return {
        "status_rc": rc_status,
        "status_out": out_status,
        "journal_rc": rc_journal,
        "journal_out": out_journal,
    }


@dataclass(frozen=True)
class _Action:
    ID: str = "systemd.takctl-web"

    def inspect(self, ctx: Context) -> int:
        unit = SystemdUnit(name=UNIT_NAME, src=_unit_src(ctx), dst=UNIT_DST)
        info = unit.inspect()
        if info.get("status") == "missing-src":
            print(f"ERROR: source unit not found: {info.get('src')}")
            return 1

        print(f"Systemd unit: {UNIT_NAME}")
        print(f"  src: {info['src']}")
        print(f"  dst: {info['dst']}")
        print(f"  src sha256: {info['src_sha256']}")
        print(f"  dropin src dir: {_dropin_src_dir(ctx)}")
        print(f"  dropin src exists: {str(_dropin_src_dir(ctx).is_dir()).lower()}")

        if info["status"] == "not-installed":
            print("  status: not installed")
        else:
            print(f"  dst sha256: {info['dst_sha256']}")
            print(f"  status: {info['status']}")
            if info["status"] == "differs":
                print("  diff:")
                print(info.get("diff") or "(no diff output)")

        print("  runtime:")
        print(json.dumps(_collect_runtime_state(), indent=2, sort_keys=True))
        return 0

    def apply(self, ctx: Context) -> int:
        unit = SystemdUnit(name=UNIT_NAME, src=_unit_src(ctx), dst=UNIT_DST)
        info = unit.inspect()
        if info.get("status") == "missing-src":
            print(f"ERROR: source unit not found: {info.get('src')}")
            return 1

        expected_apply_ts = _read_apply_ts_from_state()
        before = _collect_runtime_state()

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

        rc, out = _ensure_enabled_and_started()
        if rc != 0:
            print("ERROR: failed to reenable/enable/restart takctl-web")
            print(out)
            payload = {
                "unit": UNIT_NAME,
                "before": before,
                "after": _collect_runtime_state(),
                "command_out": out,
            }
            payload["failure_dump"] = _short_fail_dump()
            _write_verify_state(payload)
            return 4

        after_start = _collect_runtime_state()
        if after_start.get("is_enabled") != "enabled":
            print("ERROR: takctl-web is not enabled after apply")
            payload = {
                "unit": UNIT_NAME,
                "before": before,
                "after": after_start,
                "command_out": out,
            }
            payload["failure_dump"] = _short_fail_dump()
            _write_verify_state(payload)
            return 4

        if not bool(after_start.get("wants_symlink_exists")):
            print(f"ERROR: missing wants symlink after apply: {WANTS_LINK}")
            payload = {
                "unit": UNIT_NAME,
                "before": before,
                "after": after_start,
                "command_out": out,
            }
            payload["failure_dump"] = _short_fail_dump()
            _write_verify_state(payload)
            return 4

        if not _wait_listen_8080(WAIT_LISTEN_SEC):
            payload = {
                "unit": UNIT_NAME,
                "before": before,
                "after": _collect_runtime_state(),
                "command_out": out,
            }
            payload["failure_dump"] = _short_fail_dump()
            _write_verify_state(payload)
            return 5

        ok, _last_good, _last_dict = _wait_health_stable(
            deadline_sec=WAIT_HEALTH_SEC,
            expected_apply_ts=expected_apply_ts,
        )
        if not ok:
            payload = {
                "unit": UNIT_NAME,
                "before": before,
                "after": _collect_runtime_state(),
                "command_out": out,
                "last_health_dict": _last_dict,
            }
            payload["failure_dump"] = _short_fail_dump()
            _write_verify_state(payload)
            return 5

        final = _collect_runtime_state()
        payload = {
            "unit": UNIT_NAME,
            "before": before,
            "after": final,
            "command_out": out,
            "expected_apply_ts": expected_apply_ts,
        }
        _write_verify_state(payload)

        print("Applied.")
        if expected_apply_ts:
            print(f"takctl-web ready (apply_ts_utc={expected_apply_ts})")
        else:
            print("takctl-web ready")
        print("takctl-web post-apply state:")
        print(json.dumps(final, indent=2, sort_keys=True))
        return 0


ACTION = _Action()
