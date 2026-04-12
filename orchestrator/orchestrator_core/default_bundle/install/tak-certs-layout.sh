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

read_simple_kv() {
  local path="$1"
  local key="$2"
  [ -f "$path" ] || return 1
  sed -n "s/^[[:space:]]*${key}[[:space:]]*=[[:space:]]*//p" "$path" | head -n 1 | sed -e 's/[[:space:]]*$//'
}

read_shell_assignment() {
  local p="$1"
  local key="$2"
  [ -f "$p" ] || return 1
  local v
  v="$(sed -n "s/^${key}=//p" "$p" | head -n 1)"
  [ -n "$v" ] || return 1
  case "$v" in
    \"*\") v="${v#\"}"; v="${v%\"}" ;;
    \'*\') v="${v#\'}"; v="${v%\'}" ;;
  esac
  printf '%s\n' "$v"
}

build_le_8446_pkcs12() {
  local flat="$1"
  local cert_meta="/opt/tak/certs/cert-metadata.sh"
  local boot_conf="/etc/taks-bootstrap.d/config.d/node.conf"
  local fqdn cert_pass le_dir le_cert le_key tmp

  fqdn="$(read_simple_kv "$boot_conf" node_fqdn || true)"
  if [ -z "$fqdn" ]; then
    fqdn="$(read_simple_kv "$boot_conf" fqdn || true)"
  fi
  cert_pass="$(read_shell_assignment "$cert_meta" PASS || read_trimmed_file /etc/taks/certs/PASS || true)"

  if [ -z "$fqdn" ]; then
    log "skip LE 8446 PKCS12 build: fqdn missing"
    return 0
  fi
  if [ -z "$cert_pass" ]; then
    log "skip LE 8446 PKCS12 build: cert PASS missing"
    return 0
  fi

  le_dir="/etc/letsencrypt/live/$fqdn"
  le_cert="$le_dir/fullchain.pem"
  le_key="$le_dir/privkey.pem"

  if [ ! -f "$le_cert" ] || [ ! -f "$le_key" ]; then
    log "skip LE 8446 PKCS12 build: missing letsencrypt lineage for $fqdn"
    return 0
  fi

  tmp="$(mktemp)"
  openssl pkcs12 -export \
    -out "$tmp" \
    -inkey "$le_key" \
    -in "$le_cert" \
    -name "$fqdn" \
    -passout pass:"$cert_pass" >/dev/null 2>&1

  install -m 0600 "$tmp" "$flat/02_SERVER/takserver-le-8446.p12"
  rm -f "$tmp"
  log "built $flat/02_SERVER/takserver-le-8446.p12 from letsencrypt lineage for $fqdn"
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

  build_le_8446_pkcs12 "$flat"

  log "layout ready:"
  log "  CA:      $flat/00_CA"
  log "  TRUST:   $flat/01_TRUST"
  log "  SERVER:  $flat/02_SERVER"
  log "  source prefix:     ${src_prefix:-<none>}"
  log "  server basename:   $server_base"
}

main "$@"
