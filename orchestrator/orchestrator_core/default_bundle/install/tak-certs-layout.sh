#!/usr/bin/env bash
set -euo pipefail

log() {
  printf '[tak-certs-layout] %s\n' "$*"
}

die() {
  printf '[tak-certs-layout] ERROR: %s\n' "$*" >&2
  exit 1
}

require_root() {
  [ "$(id -u)" -eq 0 ] || die "must run as root"
}

read_simple_kv() {
  local path="$1"
  local key="$2"
  [ -f "$path" ] || die "required file missing: $path"
  sed -n "s/^[[:space:]]*${key}[[:space:]]*=[[:space:]]*//p" "$path" | head -n 1 | sed -e 's/[[:space:]]*$//'
}

read_shell_assignment() {
  local p="$1"
  local key="$2"
  [ -f "$p" ] || die "required file missing: $p"
  local v
  v="$(sed -n "s/^${key}=//p" "$p" | head -n 1)"
  [ -n "$v" ] || die "missing shell assignment ${key} in $p"
  case "$v" in
    \"*\") v="${v#\"}"; v="${v%\"}" ;;
    \'*\') v="${v#\'}"; v="${v%\'}" ;;
  esac
  printf '%s\n' "$v"
}

require_boot_fqdn() {
  local boot_conf="/etc/taks-bootstrap.d/config.d/node.conf"
  local fqdn=""
  fqdn="$(read_simple_kv "$boot_conf" node_fqdn || true)"
  if [ -z "$fqdn" ]; then
    fqdn="$(read_simple_kv "$boot_conf" fqdn || true)"
  fi
  [ -n "$fqdn" ] || die "missing node_fqdn/fqdn in $boot_conf"
  printf '%s\n' "$fqdn"
}

reset_dir() {
  local d="$1"
  rm -rf "$d"
  mkdir -p "$d"
}

install_with_policy() {
  local src="$1"
  local dst="$2"
  local mode owner_group

  case "$dst" in
    *.p12|*.jks)
      mode="0640"
      owner_group="tak"
      ;;
    *.key)
      mode="0600"
      owner_group="root"
      ;;
    *)
      mode="0644"
      owner_group="root"
      ;;
  esac

  mkdir -p "$(dirname "$dst")"
  if [ "$owner_group" = "tak" ] && getent group tak >/dev/null 2>&1; then
    install -m "$mode" -o root -g tak "$src" "$dst"
  else
    install -m "$mode" "$src" "$dst"
  fi
  log "installed $dst"
}

required_copy() {
  local src="$1"
  local dst="$2"
  [ -f "$src" ] || die "required file missing: $src"
  install_with_policy "$src" "$dst"
}

optional_copy() {
  local src="$1"
  local dst="$2"
  [ -f "$src" ] || return 0
  install_with_policy "$src" "$dst"
}

build_public_8446_pkcs12() {
  local flat="$1"
  local fqdn cert_pass le_dir le_cert le_key tmp dst

  fqdn="$(require_boot_fqdn)"
  cert_pass="$(read_shell_assignment /opt/tak/certs/cert-metadata.sh PASS)"

  le_dir="/etc/letsencrypt/live/$fqdn"
  le_cert="$le_dir/fullchain.pem"
  le_key="$le_dir/privkey.pem"
  dst="$flat/03_PUBLIC/takserver-le-8446.p12"

  [ -f "$le_cert" ] || die "missing letsencrypt cert: $le_cert"
  [ -f "$le_key" ] || die "missing letsencrypt key: $le_key"

  mkdir -p "$flat/03_PUBLIC"

  tmp="$(mktemp)"
  if ! openssl pkcs12 -legacy -export \
      -out "$tmp" \
      -inkey "$le_key" \
      -in "$le_cert" \
      -name "$fqdn" \
      -passout "pass:$cert_pass"
  then
    rm -f "$tmp"
    die "failed building 8446 public PKCS12 from letsencrypt lineage for $fqdn"
  fi

  install_with_policy "$tmp" "$dst"
  rm -f "$tmp"

  log "built $dst from letsencrypt lineage for $fqdn"
}

main() {
  require_root

  local cert_root="/opt/tak/certs"
  local flat="$cert_root/files"
  local fqdn server_base

  [ -d "$flat" ] || {
    log "no $flat present; skipping"
    return 0
  }

  fqdn="$(require_boot_fqdn)"
  server_base="takserver-$fqdn"

  reset_dir "$flat/00_CA"
  reset_dir "$flat/01_TRUST"
  reset_dir "$flat/02_SERVER"
  reset_dir "$flat/03_PUBLIC"

  required_copy "$flat/ca.pem"                   "$flat/00_CA/ca.pem"
  optional_copy "$flat/ca-trusted.pem"           "$flat/00_CA/ca-trusted.pem"
  optional_copy "$flat/ca-do-not-share.key"      "$flat/00_CA/ca-do-not-share.key"
  optional_copy "$flat/root-ca.pem"              "$flat/00_CA/root-ca.pem"
  optional_copy "$flat/root-ca-trusted.pem"      "$flat/00_CA/root-ca-trusted.pem"
  optional_copy "$flat/root-ca-do-not-share.key" "$flat/00_CA/root-ca-do-not-share.key"
  optional_copy "$flat/ca.crl"                   "$flat/00_CA/ca.crl"
  required_copy "$flat/ca-signing.p12"           "$flat/00_CA/ca-signing.p12"
  required_copy "$flat/ca-signing.jks"           "$flat/00_CA/ca-signing.jks"

  required_copy "$flat/truststore-root.jks"      "$flat/01_TRUST/truststore-root.jks"
  optional_copy "$flat/truststore-root.p12"      "$flat/01_TRUST/truststore-root.p12"
  required_copy "$flat/fed-truststore.jks"       "$flat/01_TRUST/fed-truststore.jks"

  required_copy "$flat/$fqdn.jks"                "$flat/02_SERVER/${server_base}.jks"
  required_copy "$flat/$fqdn.p12"                "$flat/02_SERVER/${server_base}.p12"
  required_copy "$flat/$fqdn.pem"                "$flat/02_SERVER/${server_base}.pem"
  optional_copy "$flat/$fqdn-trusted.pem"        "$flat/02_SERVER/${server_base}-trusted.pem"
  optional_copy "$flat/$fqdn.key"                "$flat/02_SERVER/${server_base}.key"
  optional_copy "$flat/$fqdn.csr"                "$flat/02_SERVER/${server_base}.csr"

  build_public_8446_pkcs12 "$flat"

  log "layout ready:"
  log "  CA:      $flat/00_CA"
  log "  TRUST:   $flat/01_TRUST"
  log "  SERVER:  $flat/02_SERVER"
  log "  PUBLIC:  $flat/03_PUBLIC"
  log "  server basename: $server_base"
}

main "$@"
