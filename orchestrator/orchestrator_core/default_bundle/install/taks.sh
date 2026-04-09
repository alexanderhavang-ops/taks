#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUNDLE_ROOT="$ROOT"

STATE_LOG="/var/log/taks-installer-state.log"

ts_now() {
  date -u +"%Y-%m-%dT%H:%M:%SZ"
}

log_state() {
  local name="$1"
  local status="$2"
  printf '%s,%s,%s\n' "$name" "$(ts_now)" "$status" >> "$STATE_LOG"
}

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
IMPORT_BOOTSTRAP_BRANDING="$TAKS_SOURCE_ROOT/tak-installer/bin/import-bootstrap-branding"

if [ ! -f "$TAK_INSTALLER" ]; then
  fail "missing tak-installer at $TAK_INSTALLER"
fi

log "running tak-installer apply from extracted bundle"
(
  cd "$TAKS_SOURCE_ROOT"
  python3 ./tak-installer/tak-installer apply
)

if [ -f "$IMPORT_BOOTSTRAP_BRANDING" ]; then
  log "importing bootstrap branding"
  (
    cd "$TAKS_SOURCE_ROOT"
    bash "$IMPORT_BOOTSTRAP_BRANDING"
  )
else
  log "skip bootstrap branding import (missing $IMPORT_BOOTSTRAP_BRANDING)"
fi

log "taks install complete"
