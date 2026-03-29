#!/usr/bin/env bash
set -euo pipefail

log() {
  printf '[tak-certs-layout] %s\n' "$*"
}

read_trimmed_file() {
  local p="$1"
  [ -f "$p" ] || return 1
  tr -d '\r' < "$p" | sed -e 's/[[:space:]]*$//' | head -n 1
}

copy_if_exists() {
  local src="$1"
  local dst="$2"

  if [ ! -f "$src" ]; then
    return 0
  fi

  mkdir -p "$(dirname "$dst")"
  install -m "$(stat -c '%a' "$src")" "$src" "$dst"
  log "installed $dst"
}

detect_server_prefix() {
  local flat="$1"

  find "$flat" -maxdepth 1 -type f -name '*.jks' ! -name 'truststore-*.jks' ! -name 'fed-truststore.jks' -printf '%f\n' \
    | sed 's/\.jks$//' \
    | sort \
    | head -n 1
}

main() {
  local cert_root="/opt/tak/certs"
  local flat="$cert_root/files"

  if [ ! -d "$flat" ]; then
    log "no $flat present; skipping"
    return 0
  fi

  local unit_id server_base src_prefix
  unit_id="$(read_trimmed_file /etc/taks/TAKS_UNIT_ID || true)"
  if [ -z "$unit_id" ]; then
    unit_id="$(hostname -s 2>/dev/null || true)"
  fi
  unit_id="$(printf '%s' "$unit_id" | tr '[:upper:]' '[:lower:]')"
  server_base="takserver-$unit_id"

  mkdir -p \
    "$flat/00_CA" \
    "$flat/01_TRUST" \
    "$flat/02_SERVER"

  copy_if_exists "$flat/ca.pem"                   "$flat/00_CA/ca.pem"
  copy_if_exists "$flat/ca-trusted.pem"           "$flat/00_CA/ca-trusted.pem"
  copy_if_exists "$flat/ca-do-not-share.key"      "$flat/00_CA/ca-do-not-share.key"
  copy_if_exists "$flat/root-ca.pem"              "$flat/00_CA/root-ca.pem"
  copy_if_exists "$flat/root-ca-trusted.pem"      "$flat/00_CA/root-ca-trusted.pem"
  copy_if_exists "$flat/root-ca-do-not-share.key" "$flat/00_CA/root-ca-do-not-share.key"
  copy_if_exists "$flat/ca.crl"                   "$flat/00_CA/ca.crl"
  copy_if_exists "$flat/ca-signing.p12"           "$flat/00_CA/ca-signing.p12"
  copy_if_exists "$flat/ca-signing.jks"           "$flat/00_CA/ca-signing.jks"

  copy_if_exists "$flat/truststore-root.jks"      "$flat/01_TRUST/truststore-root.jks"
  copy_if_exists "$flat/truststore-root.p12"      "$flat/01_TRUST/truststore-root.p12"
  copy_if_exists "$flat/fed-truststore.jks"       "$flat/01_TRUST/fed-truststore.jks"

  src_prefix="$(detect_server_prefix "$flat" || true)"
  if [ -z "$src_prefix" ]; then
    log "no server cert prefix detected under $flat"
  else
    copy_if_exists "$flat/$src_prefix.jks"         "$flat/02_SERVER/$server_base.jks"
    copy_if_exists "$flat/$src_prefix.p12"         "$flat/02_SERVER/$server_base.p12"
    copy_if_exists "$flat/$src_prefix.pem"         "$flat/02_SERVER/$server_base.pem"
    copy_if_exists "$flat/$src_prefix-trusted.pem" "$flat/02_SERVER/$server_base-trusted.pem"
    copy_if_exists "$flat/$src_prefix.key"         "$flat/02_SERVER/$server_base.key"
    copy_if_exists "$flat/$src_prefix.csr"         "$flat/02_SERVER/$server_base.csr"
  fi

  log "layout ready:"
  log "  CA:      $flat/00_CA"
  log "  TRUST:   $flat/01_TRUST"
  log "  SERVER:  $flat/02_SERVER"
  log "  source prefix:     ${src_prefix:-<none>}"
  log "  server basename:   $server_base"
}

main "$@"
