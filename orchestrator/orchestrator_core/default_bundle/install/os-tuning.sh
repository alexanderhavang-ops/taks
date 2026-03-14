#!/usr/bin/env bash
set -euo pipefail

log() {
  printf '[os-tuning] %s\n' "$*"
}

fail() {
  printf '[os-tuning] ERROR: %s\n' "$*" >&2
  exit 1
}

if [ "$(id -u)" -ne 0 ]; then
  fail "must run as root"
fi

SWAPFILE="/swapfile"
SWAPSIZE_MIB="${SWAPSIZE_MIB:-4096}"

log "current memory/swap"
free -h || true

if swapon --show --noheadings | awk '{print $1}' | grep -qx "$SWAPFILE"; then
  log "swap already active on $SWAPFILE"
else
  if [ ! -f "$SWAPFILE" ]; then
    log "creating $SWAPFILE (${SWAPSIZE_MIB} MiB)"
    fallocate -l "${SWAPSIZE_MIB}M" "$SWAPFILE" 2>/dev/null || dd if=/dev/zero of="$SWAPFILE" bs=1M count="$SWAPSIZE_MIB" status=progress
    chmod 600 "$SWAPFILE"
    mkswap "$SWAPFILE"
  else
    log "swapfile already exists: $SWAPFILE"
    chmod 600 "$SWAPFILE"
  fi

  log "enabling swap"
  swapon "$SWAPFILE"
fi

if ! grep -qE '^[[:space:]]*/swapfile[[:space:]]+none[[:space:]]+swap[[:space:]]' /etc/fstab; then
  log "persisting swap in /etc/fstab"
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
else
  log "/etc/fstab already contains swapfile entry"
fi

log "setting vm.swappiness=10"
sysctl -w vm.swappiness=10 >/dev/null

if [ -d /etc/sysctl.d ]; then
  cat > /etc/sysctl.d/60-taks-swap.conf <<'EOF'
vm.swappiness=10
EOF
fi

log "final memory/swap"
free -h || true
swapon --show || true
