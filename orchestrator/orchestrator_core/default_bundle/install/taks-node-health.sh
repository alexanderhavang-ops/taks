#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUNDLE_ROOT="$ROOT"

INSTALL_DST="/opt/taks/install/taks-node-health.sh"
LIB_DST="/opt/taks/install/taks-node-health-lib.sh"
CHECKS_DST_DIR="/opt/taks/install/taks-node-health.d"
SERVICE_DST="/etc/systemd/system/taks-node-health.service"
TIMER_DST="/etc/systemd/system/taks-node-health.timer"

OUT_DIR="/opt/tak/takctl-state"
OUT_JSON="$OUT_DIR/node-health.json"
BEDROCK_CACHE="$OUT_DIR/node-health-bedrock.json"
NODE_CONF="/etc/taks-bootstrap.d/config.d/node.conf"

CHECKS_TSV=""
TMP_JSON=""
CHECKS_DIR="$BUNDLE_ROOT/install/taks-node-health.d"
LIB_PATH="$BUNDLE_ROOT/install/taks-node-health-lib.sh"

cleanup() {
  [ -n "${CHECKS_TSV:-}" ] && rm -f "$CHECKS_TSV" || true
  [ -n "${TMP_JSON:-}" ] && rm -f "$TMP_JSON" || true
}
trap cleanup EXIT

plugin_check_id() {
  local path="$1"
  local base
  base="$(basename "$path")"
  base="${base%.check}"
  printf '%s' "$base" | tr '/ .:' '_' | tr -cd '[:alnum:]_-'
}

run_one_check() {
  local path="$1"
  local cid
  cid="$(plugin_check_id "$path")"

  unset -f health_check_main >/dev/null 2>&1 || true

  if ! source "$path"; then
    add_check "plugin_${cid}" fail warn "health plugin load failed: $(basename "$path")"
    return 0
  fi

  if ! declare -F health_check_main >/dev/null 2>&1; then
    add_check "plugin_${cid}" fail warn "health plugin missing health_check_main(): $(basename "$path")"
    return 0
  fi

  if ! health_check_main; then
    add_check "plugin_${cid}" fail warn "health plugin execution failed: $(basename "$path")"
  fi

  unset -f health_check_main >/dev/null 2>&1 || true
}

run_checks_dir() {
  local dir="$1"
  [ -d "$dir" ] || return 0

  local found=0 f
  while IFS= read -r -d '' f; do
    found=1
    run_one_check "$f"
  done < <(find "$dir" -maxdepth 1 -type f -name '*.check' -print0 | sort -z)

  if [ "$found" -eq 0 ]; then
    add_check node_health warn warn "no health plugins found under $dir"
  fi
}

run_probe() {
  CHECKS_TSV="$(mktemp)"
  # shellcheck disable=SC1090
  source "$LIB_PATH"
  run_checks_dir "$CHECKS_DIR"
  write_json
}

install_units() {
  install -d -m 0755 /opt/taks/install
  install -m 0755 "$BUNDLE_ROOT/install/taks-node-health.sh" "$INSTALL_DST"
  install -m 0644 "$BUNDLE_ROOT/install/taks-node-health-lib.sh" "$LIB_DST"

  install -d -m 0755 "$CHECKS_DST_DIR"
  find "$BUNDLE_ROOT/install/taks-node-health.d" -maxdepth 1 -type f -name '*.check' | while read -r f; do
    install -m 0644 "$f" "$CHECKS_DST_DIR/$(basename "$f")"
  done

  install -m 0644 "$BUNDLE_ROOT/install/systemd/taks-node-health.service" "$SERVICE_DST"
  install -m 0644 "$BUNDLE_ROOT/install/systemd/taks-node-health.timer" "$TIMER_DST"
  systemctl daemon-reload
  systemctl enable --now taks-node-health.timer
  systemctl start taks-node-health.service || true
  printf '[taks-node-health] installed runner+lib+checks+service+timer\n'
}

case "${1:-}" in
  --run)
    run_probe || {
      CHECKS_TSV="$(mktemp)"
      # shellcheck disable=SC1090
      source "$LIB_PATH"
      add_check node_health fail critical "node health collector crashed"
      write_json || true
    }
    ;;
  *)
    install_units
    ;;
esac
