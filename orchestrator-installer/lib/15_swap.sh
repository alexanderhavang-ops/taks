#!/usr/bin/env bash
set -euo pipefail

ensure_swap(){
  local swapfile="${1:-/swapfile}"
  local gb="${2:-4}"

  if swapon --show | awk '{print $1}' | grep -qx "$swapfile"; then
    return 0
  fi

  log "ensure_swap: creating ${gb}G swap at ${swapfile}"
  if command -v fallocate >/dev/null 2>&1; then
    fallocate -l "${gb}G" "$swapfile" || true
  fi
  if [ ! -s "$swapfile" ]; then
    dd if=/dev/zero of="$swapfile" bs=1M count=$((gb*1024))
  fi

  chmod 600 "$swapfile"
  mkswap "$swapfile" >/dev/null
  swapon "$swapfile"

  grep -q "^${swapfile} " /etc/fstab || echo "${swapfile} none swap sw 0 0" >> /etc/fstab
  log "ensure_swap: enabled"
}
