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

curl -fsS \
  -u "${TAKS_NODE_USER}:${TAKS_NODE_PASSWORD}" \
  -H 'Content-Type: application/json' \
  -d "$(cat <<JSON
{
  "node_id": "${NODE_ID}",
  "unit_path": "${UNIT_ID}",
  "role": "tak-node",
  "fqdn": "${NODE_FQDN}",
  "hostname": "${NODE_HOSTNAME}",
  "private_ip": "${PRIVATE_IP}",
  "status": "online"
}
JSON
)" \
  "${ORCH_API_URL%/}/api/v2/nodes/heartbeat" >/dev/null
