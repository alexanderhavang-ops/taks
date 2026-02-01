#!/usr/bin/env bash
set -euo pipefail

cert_layout_create(){
  local root="/opt/tak/certs/files"

  log "Ensuring cert layout under $root"

  install -d -m 0755 "$root"
  install -d -m 0750 "$root/00_CA"
  install -d -m 0755 "$root/01_TRUST" "$root/02_SERVER" "$root/03_FEDERATION" \
                    "$root/04_USERS" "$root/05_CSRS" "$root/06_CONFIG" \
                    "$root/07_MISC" "$root/99_ARCHIVE"

  if [[ ! -f "$root/ca.crl" ]]; then
    install -m 0644 /dev/null "$root/ca.crl"
  fi

  chown -R root:root "$root/00_CA"
  chmod 0750 "$root/00_CA"

  chown -R root:root \
    "$root/01_TRUST" "$root/02_SERVER" "$root/03_FEDERATION" \
    "$root/04_USERS" "$root/05_CSRS" "$root/06_CONFIG" \
    "$root/07_MISC" "$root/99_ARCHIVE" "$root/ca.crl" || true

  chmod 0644 "$root/ca.crl" || true
}
