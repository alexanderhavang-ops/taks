#!/usr/bin/env bash
set -euo pipefail

NODE_ENV=""
for cand in \
  /etc/taks-bootstrap.d/node.env \
  /etc/taks/node.env
do
  if [[ -f "$cand" ]]; then
    NODE_ENV="$cand"
    break
  fi
done

UNIT_JSON=/etc/taks/unit.json
INSTALL_STATE_LOG=/var/log/taks-installer-state.log

[[ -n "$NODE_ENV" ]] || {
  echo "[taks-heartbeat] no node.env found in /etc/taks-bootstrap.d or /etc/taks" >&2
  exit 0
}

# shellcheck disable=SC1090
. "$NODE_ENV"

ORCH_API_URL="${ORCH_API_URL:-}"
TAKS_NODE_USER="${TAKS_NODE_USER:-}"
TAKS_NODE_PASSWORD="${TAKS_NODE_PASSWORD:-}"

[[ -n "$ORCH_API_URL" ]] || {
  echo "[taks-heartbeat] ORCH_API_URL missing in $NODE_ENV" >&2
  exit 0
}
[[ -n "$TAKS_NODE_USER" ]] || {
  echo "[taks-heartbeat] TAKS_NODE_USER missing in $NODE_ENV" >&2
  exit 0
}
[[ -n "$TAKS_NODE_PASSWORD" ]] || {
  echo "[taks-heartbeat] TAKS_NODE_PASSWORD missing in $NODE_ENV" >&2
  exit 0
}

UNIT_ID=""
if command -v jq >/dev/null 2>&1 && [[ -f "$UNIT_JSON" ]]; then
  UNIT_ID="$(jq -r '.unit_id // .unit_path // empty' "$UNIT_JSON" 2>/dev/null || true)"
fi

NODE_ID="${TAKS_NODE_ID:-${TAKS_NODE_FQDN:-$(hostname -f 2>/dev/null || hostname)}}"
NODE_FQDN="${TAKS_NODE_FQDN:-$NODE_ID}"

if [[ -n "${TAKS_NODE_HOSTNAME:-}" ]]; then
  NODE_HOSTNAME="$TAKS_NODE_HOSTNAME"
elif [[ -n "${TAKS_NODE_FQDN:-}" ]]; then
  NODE_HOSTNAME="${TAKS_NODE_FQDN%%.*}"
else
  NODE_HOSTNAME="$(hostname -s 2>/dev/null || hostname)"
fi

PRIVATE_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"

payload="$(
  NODE_ID="$NODE_ID" \
  UNIT_ID="$UNIT_ID" \
  NODE_FQDN="$NODE_FQDN" \
  NODE_HOSTNAME="$NODE_HOSTNAME" \
  PRIVATE_IP="$PRIVATE_IP" \
  INSTALL_STATE_LOG="$INSTALL_STATE_LOG" \
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

print(json.dumps(payload, separators=(",", ":")))
PY
)"

curl -fsS \
  -u "${TAKS_NODE_USER}:${TAKS_NODE_PASSWORD}" \
  -H 'Content-Type: application/json' \
  -d "$payload" \
  "${ORCH_API_URL%/}/api/v2/nodes/heartbeat" >/dev/null
