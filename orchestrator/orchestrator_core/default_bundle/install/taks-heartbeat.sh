#!/usr/bin/env bash
set -euo pipefail

NODE_ENV=/etc/taks/node.env
UNIT_JSON=/etc/taks/unit.json

[[ -f "$NODE_ENV" ]] || exit 0
# shellcheck disable=SC1090
. "$NODE_ENV"

ORCH_API_URL="${ORCH_API_URL:-}"
TAKS_NODE_USER="${TAKS_NODE_USER:-}"
TAKS_NODE_PASSWORD="${TAKS_NODE_PASSWORD:-}"

[[ -n "$ORCH_API_URL" ]] || exit 0
[[ -n "$TAKS_NODE_USER" ]] || exit 0
[[ -n "$TAKS_NODE_PASSWORD" ]] || exit 0

UNIT_ID=""
if command -v jq >/dev/null 2>&1 && [[ -f "$UNIT_JSON" ]]; then
  UNIT_ID="$(jq -r '.unit_id // empty' "$UNIT_JSON" 2>/dev/null || true)"
fi

NODE_ID="${TAKS_NODE_ID:-${TAKS_NODE_FQDN:-$(hostname -f 2>/dev/null || hostname)}}"
NODE_FQDN="${TAKS_NODE_FQDN:-$NODE_ID}"
NODE_HOSTNAME="${TAKS_NODE_HOSTNAME:-$(hostname -s 2>/dev/null || hostname)}"
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
