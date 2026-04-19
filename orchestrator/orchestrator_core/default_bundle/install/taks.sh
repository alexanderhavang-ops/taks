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
TAKCTL_RUNTIME_ROOT="/opt/tak/tools/takctl"
DOCS_SYNC_SCRIPT="$TAKCTL_RUNTIME_ROOT/bin/takctl-docs-sync-documents"
DOCS_SYNC_PY="$TAKCTL_RUNTIME_ROOT/.venv/bin/python"

seed_runtime_documents_from_bundle() {
  local src_dir="$BUNDLE_ROOT/documents"
  local dst_dir="/opt/tak/tools/takctl/data/library/documents"
  local src rel dst
  local -a docs=()

  if [ ! -d "$src_dir" ]; then
    log "skip runtime Documents seed (missing $src_dir)"
    return 0
  fi

  mapfile -t docs < <(find "$src_dir" -type f \( -iname '*.pdf' -o -iname '*.zip' \) | sort)

  if [ "${#docs[@]}" -eq 0 ]; then
    log "skip runtime Documents seed (no .pdf/.zip in $src_dir)"
    return 0
  fi

  mkdir -p "$dst_dir"

  for src in "${docs[@]}"; do
    rel="${src#$src_dir/}"
    dst="$dst_dir/$rel"
    mkdir -p "$(dirname "$dst")"
    install -m 0644 "$src" "$dst"
  done

  chown -R tak:tak "$dst_dir" 2>/dev/null || true
  log "seeded runtime Documents from bundle documents into $dst_dir (${#docs[@]} files)"
}

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

seed_runtime_documents_from_bundle

if [ -f "$DOCS_SYNC_SCRIPT" ] && [ -x "$DOCS_SYNC_PY" ]; then
  log "syncing runtime Documents into Martine docs state"
  if ! PYTHONPATH="$TAKCTL_RUNTIME_ROOT" "$DOCS_SYNC_PY" "$DOCS_SYNC_SCRIPT"; then
    log "WARNING: runtime Documents sync failed"
  fi
else
  log "skip runtime Documents sync (missing $DOCS_SYNC_SCRIPT or $DOCS_SYNC_PY)"
fi

log "taks install complete"
