#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUNDLE_ROOT="$ROOT"

log() {
  printf '[taks] %s\n' "$*"
}

fail() {
  printf '[taks] ERROR: %s\n' "$*" >&2
  exit 1
}

if [ "$(id -u)" -ne 0 ]; then
  fail "must run as root"
fi

TAKS_SOURCE_ROOT="$BUNDLE_ROOT/taks-source"
TAK_INSTALLER="$TAKS_SOURCE_ROOT/tak-installer/tak-installer"

if [ ! -f "$TAK_INSTALLER" ]; then
  fail "missing tak-installer at $TAK_INSTALLER"
fi

NODE_ENV="$BUNDLE_ROOT/install/node.env"
if [ -f "$NODE_ENV" ]; then
  # shellcheck disable=SC1090
  . "$NODE_ENV"
  log "loaded $NODE_ENV"
else
  log "no install/node.env present"
fi

if [ -n "${TAKS_NODE_FQDN:-}" ]; then
  export TAKS_FQDN="${TAKS_NODE_FQDN}"
  export FQDN="${TAKS_NODE_FQDN}"
fi

if [ -n "${TAKS_NODE_CERT_MODEL:-}" ]; then
  export TAKS_NODE_CERT_MODEL
fi

if [ -n "${LE_EMAIL:-}" ]; then
  export LE_EMAIL
fi

log "running tak-installer apply from extracted bundle"
(
  cd "$TAKS_SOURCE_ROOT"
  python3 ./tak-installer/tak-installer apply
)

log "taks install complete"
