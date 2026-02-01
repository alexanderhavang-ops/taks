#!/usr/bin/env bash
set -euo pipefail

call_home(){
  # No-op unless ORCH_URL is set
  local url="${ORCH_URL:-}"
  [[ -n "$url" ]] || { log "call_home: ORCH_URL not set (skipping)"; return 0; }

  command -v curl >/dev/null 2>&1 || { log "call_home: curl missing (skipping)"; return 0; }

  # Best-effort: never fail the install
  local payload tmp rc
  tmp="$(mktemp)"
  payload="$(cat <<JSON
{
  "battalion": "${BATTALION}",
  "fqdn": "${FQDN}",
  "base_domain": "${BASE_DOMAIN}",
  "public_port_enroll": ${PUBLIC_PORT_ENROLL},
  "install_mode": "${INSTALL_MODE}",
  "timestamp": "$(date -Is)"
}
JSON
)"

  printf '%s\n' "$payload" >"$tmp"

  log "call_home: POST $url"
  set +e
  curl -fsS -m 5 \
    -H "Content-Type: application/json" \
    --data-binary @"$tmp" \
    "$url" >/dev/null 2>&1
  rc=$?
  set -e
  rm -f "$tmp" || true

  if [[ $rc -eq 0 ]]; then
    log "call_home: OK"
  else
    log "call_home: failed (rc=$rc) - ignored"
  fi

  return 0
}
