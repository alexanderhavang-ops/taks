from __future__ import annotations

import json
import subprocess
import urllib.request
from pathlib import Path
from typing import Any, Optional

from takctl.appctx import AppContext


def _http_get_json(url: str, timeout_sec: float = 2.0) -> tuple[int, Optional[dict[str, Any]], Optional[str]]:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as r:
            code = int(getattr(r, "status", 200))
            raw = r.read().decode("utf-8", "replace").strip()
            if not raw:
                return code, None, None
            try:
                return code, json.loads(raw), None
            except Exception:
                return code, None, f"Non-JSON response: {raw[:200]}"
    except Exception as e:
        return 0, None, str(e)


def _systemd_show(unit: str) -> dict[str, Any]:
    """
    Best-effort systemd state. Never raises.
    """
    keys = ["ActiveState", "SubState", "LoadState", "UnitFileState", "Description", "Result"]
    props = ",".join(keys)
    try:
        p = subprocess.run(
            ["systemctl", "show", unit, f"--property={props}", "--no-pager"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        out: dict[str, Any] = {"unit": unit}
        if p.returncode != 0:
            out["error"] = (p.stderr.strip() or f"systemctl show rc={p.returncode}")
            return out

        for line in p.stdout.splitlines():
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            out[k] = v
        return out
    except Exception as e:
        return {"unit": unit, "error": str(e)}


def llm_status(_ctx: AppContext) -> dict[str, Any]:
    # Minimal v2: local payload awareness + systemd state + health probe
    base = "http://127.0.0.1:8090"
    unit = "llm-local.service"

    payload_present = Path("/opt/llm").exists()
    sd = _systemd_show(unit)

    active = (sd.get("ActiveState") or "").lower()
    sub = (sd.get("SubState") or "").lower()
    load = (sd.get("LoadState") or "").lower()

    # Decide whether to probe HTTP:
    # - If payload is present, probe (even if unit is down; tells operator what's wrong)
    # - If systemd says it's active/running, probe
    # - Otherwise skip probe to avoid misleading "connection refused" on nodes without /opt/llm
    should_probe = bool(payload_present) or (active == "active") or (sub == "running")

    code: int = 0
    body: Optional[dict[str, Any]] = None
    err: Optional[str] = None

    if should_probe:
        code, body, err = _http_get_json(f"{base}/health", timeout_sec=2.0)

    ok = bool(code == 200 and isinstance(body, dict) and body.get("status") == "ok")

    return {
        "url": base,
        "unit": unit.replace(".service", ""),
        "local_payload_present": bool(payload_present),
        "systemd": {
            "active": sd.get("ActiveState"),
            "sub": sd.get("SubState"),
            "load": sd.get("LoadState"),
            "unit_file_state": sd.get("UnitFileState"),
            "result": sd.get("Result"),
            "description": sd.get("Description"),
            "error": sd.get("error"),
        },
        "health": {
            "ok": bool(ok),
            "status_code": (code or None) if should_probe else None,
            "body": body,
            "error": err if should_probe else None,
            "probed": bool(should_probe),
        },
    }

