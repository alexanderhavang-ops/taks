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

if [ ! -x "$BUNDLE_ROOT/tak-installer/tak-installer" ]; then
  fail "missing tak-installer at $BUNDLE_ROOT/tak-installer/tak-installer"
fi

log "running tak-installer apply from extracted bundle"
(
  cd "$BUNDLE_ROOT"
  ./tak-installer/tak-installer apply
)

log "taks install complete"
