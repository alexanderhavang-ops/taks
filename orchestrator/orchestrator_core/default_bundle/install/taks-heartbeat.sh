#!/usr/bin/env bash
set -euo pipefail

UNIT_JSON=/etc/taks/unit.json
INSTALL_STATE_LOG=/var/log/taks-installer-state.log
NODE_HEALTH_JSON=/opt/tak/takctl-state/node-health.json

read_runtime_values() {
  python3 - <<'PY'
from __future__ import annotations

import json
from pathlib import Path


def parse_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip()
        if k:
            out[k] = v
    return out


def load_dir(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_dir():
        return out
    for p in sorted(path.glob("*.conf")):
        out.update(parse_file(p))
    return out


conf = {}
for d in (
    Path("/opt/tak/tools/takctl/conf.d"),
    Path("/etc/taks-bootstrap.d/config.d"),
):
    conf.update(load_dir(d))

sec = {}
for d in (
    Path("/opt/tak/tools/takctl/secrets.d"),
    Path("/etc/taks-bootstrap.d/secrets.d"),
):
    sec.update(load_dir(d))

payload = {
    "ORCH_API_URL": str(conf.get("orch_api_url", "") or ""),
    "TAKS_NODE_USER": str(sec.get("node_api_user", "") or sec.get("node_user", "") or ""),
    "TAKS_NODE_PASSWORD": str(sec.get("node_api_password", "") or sec.get("node_password", "") or ""),
    "NODE_ID": str(conf.get("node_id", "") or conf.get("node_fqdn", "") or conf.get("fqdn", "") or ""),
    "NODE_FQDN": str(conf.get("node_fqdn", "") or conf.get("fqdn", "") or ""),
    "NODE_HOSTNAME": str(conf.get("hostname", "") or ""),
}

for k, v in payload.items():
    print(f"{k}={json.dumps(v)}")
PY
}

eval "$(read_runtime_values)"

[[ -n "$ORCH_API_URL" ]] || {
  echo "[taks-heartbeat] orch_api_url missing in runtime/bootstrap conf.d" >&2
  exit 0
}
[[ -n "$TAKS_NODE_USER" ]] || {
  echo "[taks-heartbeat] node_api_user missing in runtime/bootstrap secrets.d" >&2
  exit 0
}
[[ -n "$TAKS_NODE_PASSWORD" ]] || {
  echo "[taks-heartbeat] node_api_password missing in runtime/bootstrap secrets.d" >&2
  exit 0
}

UNIT_ID=""
if command -v jq >/dev/null 2>&1 && [[ -f "$UNIT_JSON" ]]; then
  UNIT_ID="$(jq -r '.unit_id // .unit_path // empty' "$UNIT_JSON" 2>/dev/null || true)"
fi

if [[ -z "$NODE_ID" ]]; then
  NODE_ID="$(hostname -f 2>/dev/null || hostname)"
fi

if [[ -z "$NODE_FQDN" ]]; then
  NODE_FQDN="$NODE_ID"
fi

if [[ -z "$NODE_HOSTNAME" ]]; then
  if [[ -n "$NODE_FQDN" ]]; then
    NODE_HOSTNAME="${NODE_FQDN%%.*}"
  else
    NODE_HOSTNAME="$(hostname -s 2>/dev/null || hostname)"
  fi
fi

PRIVATE_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"

payload="$(
  NODE_ID="$NODE_ID" \
  UNIT_ID="$UNIT_ID" \
  NODE_FQDN="$NODE_FQDN" \
  NODE_HOSTNAME="$NODE_HOSTNAME" \
  PRIVATE_IP="$PRIVATE_IP" \
  INSTALL_STATE_LOG="$INSTALL_STATE_LOG" \
  NODE_HEALTH_JSON="$NODE_HEALTH_JSON" \
  python3 - <<'PY'
from __future__ import annotations

import csv
import json
import os
from collections import OrderedDict


def event_state(raw_status: str) -> str:
    s = (raw_status or "").strip().lower()
    if s == "succeeded":
        return "succeeded"
    if s == "failed":
        return "failed"
    if s == "started":
        return "running"
    return "unknown"


def step_state(raw_status: str, *, main_succeeded: bool, name: str) -> str:
    s = (raw_status or "").strip().lower()
    if s == "succeeded":
        return "succeeded"
    if s == "failed":
        return "failed"
    if s == "started":
        if main_succeeded and name != "install/main":
            return "incomplete"
        return "running"
    return "unknown"


def parse_install_log(path: str):
    if not path or not os.path.isfile(path):
        return None

    steps_map = OrderedDict()
    events = []

    with open(path, "r", encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        for row in reader:
            if len(row) < 3:
                continue

            name = (row[0] or "").strip()
            ts = (row[1] or "").strip()
            status = (row[2] or "").strip()
            if not name:
                continue

            events.append({
                "name": name,
                "ts": ts,
                "status": status,
                "state": event_state(status),
            })

            cur = steps_map.get(name)
            if cur is None:
                cur = {
                    "name": name,
                    "first_ts": ts,
                    "last_ts": ts,
                    "status": status,
                    "state": "unknown",
                    "event_count": 0,
                }
                steps_map[name] = cur

            cur["last_ts"] = ts
            cur["status"] = status
            cur["event_count"] = int(cur["event_count"]) + 1

    if not steps_map:
        return None

    main_status = str(steps_map.get("install/main", {}).get("status") or "")
    main_succeeded = main_status.strip().lower() == "succeeded"

    steps = list(steps_map.values())
    for step in steps:
        step["state"] = step_state(
            str(step.get("status") or ""),
            main_succeeded=main_succeeded,
            name=str(step.get("name") or ""),
        )

    leaf_steps = [s for s in steps if s.get("name") != "install/main"]
    total_steps = len(leaf_steps)
    completed_steps = sum(1 for s in leaf_steps if s.get("state") == "succeeded")
    failed_steps = sum(1 for s in leaf_steps if s.get("state") == "failed")
    running_steps = sum(1 for s in leaf_steps if s.get("state") == "running")
    incomplete_steps = sum(1 for s in leaf_steps if s.get("state") == "incomplete")

    if failed_steps:
        summary_state = "failed"
    elif main_succeeded and incomplete_steps:
        summary_state = "completed_with_warnings"
    elif main_succeeded:
        summary_state = "succeeded"
    elif running_steps or completed_steps:
        summary_state = "running"
    else:
        summary_state = "unknown"

    if main_succeeded:
        progress_pct = 100
    elif total_steps > 0:
        progress_pct = int((completed_steps * 100) / total_steps)
    else:
        progress_pct = 0

    return {
        "source": path,
        "summary": {
            "state": summary_state,
            "main_state": step_state(main_status, main_succeeded=main_succeeded, name="install/main") if main_status else "unknown",
            "progress_pct": progress_pct,
            "total_steps": total_steps,
            "completed_steps": completed_steps,
            "failed_steps": failed_steps,
            "running_steps": running_steps,
            "incomplete_steps": incomplete_steps,
            "warning_steps": incomplete_steps,
            "last_event_ts": events[-1]["ts"] if events else None,
        },
        "steps": steps,
        "events": events,
    }


def load_node_health(path: str):
    if not path or not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None

    out = {}
    rollup = data.get("rollup")
    checks = data.get("checks")
    if isinstance(rollup, dict):
        out["services"] = rollup
    if isinstance(checks, dict):
        out["checks"] = checks
    return out or None


payload = {
    "node_id": os.environ.get("NODE_ID", ""),
    "unit_path": os.environ.get("UNIT_ID", ""),
    "role": "tak-node",
    "fqdn": os.environ.get("NODE_FQDN", ""),
    "hostname": os.environ.get("NODE_HOSTNAME", ""),
    "private_ip": os.environ.get("PRIVATE_IP", ""),
    "status": "online",
}

install = parse_install_log(os.environ.get("INSTALL_STATE_LOG", ""))
if install is not None:
    payload["install"] = install

node_health = load_node_health(os.environ.get("NODE_HEALTH_JSON", ""))
if node_health is not None:
    payload.update(node_health)

print(json.dumps(payload, separators=(",", ":")))
PY
)"

curl -fsS \
  -u "${TAKS_NODE_USER}:${TAKS_NODE_PASSWORD}" \
  -H 'Content-Type: application/json' \
  -d "$payload" \
  "${ORCH_API_URL%/}/api/v2/nodes/heartbeat" >/dev/null
