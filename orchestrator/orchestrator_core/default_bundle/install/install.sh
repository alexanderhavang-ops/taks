#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUNDLE_ROOT="$ROOT"

log() {
  printf '[install] %s\n' "$*"
}

run_step() {
  local name="$1"
  local path="$2"

  if [ ! -f "$path" ]; then
    log "skip $name (missing: $path)"
    return 0
  fi

  log "running $name: $path"
  bash "$path"
}

install_base_files() {
  mkdir -p /etc/taks

  if [ -f "$BUNDLE_ROOT/config/unit.json" ]; then
    install -m 0644 "$BUNDLE_ROOT/config/unit.json" /etc/taks/unit.json
    log "installed /etc/taks/unit.json"
  fi

  if [ -f "$BUNDLE_ROOT/install/node.env" ]; then
    install -m 0600 "$BUNDLE_ROOT/install/node.env" /etc/taks/node.env
    log "installed /etc/taks/node.env"
  fi
}

install_bundled_tls_material() {
  local node_env="/etc/taks/node.env"
  local src_dir="$BUNDLE_ROOT/install/letsencrypt"
  local src_cert="$src_dir/fullchain.pem"
  local src_key="$src_dir/privkey.pem"

  if [ ! -f "$node_env" ]; then
    log "skip bundled TLS install (missing /etc/taks/node.env)"
    return 0
  fi

  # shellcheck disable=SC1090
  . "$node_env"

  local fqdn="${TAKS_NODE_FQDN:-}"
  if [ -z "$fqdn" ]; then
    log "skip bundled TLS install (TAKS_NODE_FQDN missing)"
    return 0
  fi

  if [ ! -f "$src_cert" ] || [ ! -f "$src_key" ]; then
    log "skip bundled TLS install (missing bundled cert/key)"
    return 0
  fi

  local dst_dir="/etc/letsencrypt/live/$fqdn"
  mkdir -p "$dst_dir"

  install -m 0644 "$src_cert" "$dst_dir/fullchain.pem"
  install -m 0600 "$src_key" "$dst_dir/privkey.pem"

  log "installed bundled TLS material into $dst_dir"
}

install_heartbeat() {
  mkdir -p /opt/taks/install
  install -m 0755 "$BUNDLE_ROOT/install/taks-heartbeat.sh" /opt/taks/install/taks-heartbeat.sh
  install -m 0644 "$BUNDLE_ROOT/install/systemd/taks-heartbeat.service" /etc/systemd/system/taks-heartbeat.service
  install -m 0644 "$BUNDLE_ROOT/install/systemd/taks-heartbeat.timer" /etc/systemd/system/taks-heartbeat.timer

  systemctl daemon-reload

  if [ -f /etc/taks/node.env ]; then
    systemctl enable --now taks-heartbeat.timer
    log "enabled taks-heartbeat.timer"
  else
    log "node.env missing, not enabling taks-heartbeat.timer"
  fi
}

main() {
  install_base_files
  install_bundled_tls_material
  install_heartbeat

  run_step "os-tuning" "$BUNDLE_ROOT/install/os-tuning.sh"
  run_step "takserver" "$BUNDLE_ROOT/install/takserver.sh"

  if [ -f "$BUNDLE_ROOT/install/taks.sh" ]; then
    if bash "$BUNDLE_ROOT/install/taks.sh"; then
      log "taks step completed"
    else
      log "WARNING: taks step failed; continuing"
    fi
  fi

  log "install complete"
}

main "$@"
