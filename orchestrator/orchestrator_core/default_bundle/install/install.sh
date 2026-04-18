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
  printf '[install] %s\n' "$*"
}

read_simple_kv() {
  local path="$1"
  local key="$2"
  [ -f "$path" ] || return 1
  sed -n "s/^[[:space:]]*${key}[[:space:]]*=[[:space:]]*//p" "$path" | head -n 1 | sed -e 's/[[:space:]]*$//'
}

read_trimmed_file() {
  local p="$1"
  [ -f "$p" ] || return 1
  tr -d '\r' < "$p" | sed -e 's/[[:space:]]*$//' | head -n 1
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

run_step() {
  local name="$1"
  local path="$2"

  if [ ! -f "$path" ]; then
    log "skip $name (missing: $path)"
    return 0
  fi

  log_state "$name" "Started"
  log "running $name: $path"
  bash "$path"
  log_state "$name" "Succeeded"
}

install_keystore_file() {
  local src="$1"
  local dst="$2"
  mkdir -p "$(dirname "$dst")"
  if getent group tak >/dev/null 2>&1; then
    install -m 0640 -o root -g tak "$src" "$dst"
  else
    install -m 0640 "$src" "$dst"
  fi
}

ensure_ca_signing_keystore() {
  local cert_dir="/opt/tak/certs"
  local files_dir="$cert_dir/files"

  if [ ! -d "$files_dir" ]; then
    log "skip CA signing keystore generation (missing $files_dir)"
    return 0
  fi

  if [ -f "$files_dir/ca-signing.p12" ] && [ -f "$files_dir/ca-signing.jks" ]; then
    log "CA signing keystore already present"
    return 0
  fi

  if [ ! -f "$cert_dir/cert-metadata.sh" ]; then
    log "skip CA signing keystore generation (missing $cert_dir/cert-metadata.sh)"
    return 0
  fi

  # shellcheck disable=SC1090
  . "$cert_dir/cert-metadata.sh"

  local capass="${CAPASS:-atakatak}"
  local alias="tak-ca"

  if [ ! -f "$files_dir/ca.pem" ] || [ ! -f "$files_dir/ca-do-not-share.key" ]; then
    log "skip CA signing keystore generation (missing ca.pem or ca-do-not-share.key)"
    return 0
  fi

  log "generating CA signing keystore from root CA material"
  (
    cd "$files_dir"
    openssl pkcs12 -legacy -export \
      -in ca.pem \
      -inkey ca-do-not-share.key \
      -out ca-signing.p12 \
      -name "$alias" \
      -passin "pass:$capass" \
      -passout "pass:$capass"

    keytool -importkeystore \
      -deststorepass "$capass" \
      -destkeypass "$capass" \
      -destkeystore ca-signing.jks \
      -srckeystore ca-signing.p12 \
      -srcstoretype PKCS12 \
      -srcstorepass "$capass" \
      -alias "$alias" \
      -noprompt
  )

}

generate_tak_server_certs() {
  local node_conf="/etc/taks-bootstrap.d/config.d/node.conf"
  local cert_dir="/opt/tak/certs"
  local fqdn

  if [ ! -d "$cert_dir" ]; then
    log "skip cert generation (missing $cert_dir)"
    return 0
  fi

  if [ ! -f "$node_conf" ]; then
    log "skip cert generation (missing $node_conf)"
    return 0
  fi

  fqdn="$(read_simple_kv "$node_conf" node_fqdn || true)"
  if [ -z "$fqdn" ]; then
    fqdn="$(read_simple_kv "$node_conf" fqdn || true)"
  fi
  if [ -z "$fqdn" ]; then
    log "skip cert generation (node_fqdn/fqdn missing in $node_conf)"
    return 0
  fi

  if [ -f "$cert_dir/files/ca.pem" ] && [ -f "$cert_dir/files/${fqdn}.jks" ]; then
    log "cert material already present for $fqdn"
    ensure_ca_signing_keystore
    return 0
  fi

  if [ ! -f "$cert_dir/cert-metadata.sh" ]; then
    log "skip cert generation (missing $cert_dir/cert-metadata.sh)"
    return 0
  fi

  log "generating TAK root CA"
  (
    cd "$cert_dir"
    bash ./makeRootCa.sh <<'EOT'

EOT
  )

  log "generating TAK server cert for $fqdn"
  (
    cd "$cert_dir"
    bash ./makeCert.sh server "$fqdn"
  )

  ensure_ca_signing_keystore
}

normalize_server_keystores() {
  local node_conf="/etc/taks-bootstrap.d/config.d/node.conf"
  local cert_dir="/opt/tak/certs"
  local files_dir="$cert_dir/files"
  local fqdn=""
  local cert_pass=""
  local src_key src_pem dst_p12 dst_jks alias
  local tmpdir=""
  local tmppass=""
  local check_p12=""

  if [ ! -d "$files_dir" ]; then
    log "skip server keystore normalization (missing $files_dir)"
    return 0
  fi

  if [ ! -f "$node_conf" ]; then
    log "skip server keystore normalization (missing $node_conf)"
    return 0
  fi

  fqdn="$(read_simple_kv "$node_conf" node_fqdn || true)"
  if [ -z "$fqdn" ]; then
    fqdn="$(read_simple_kv "$node_conf" fqdn || true)"
  fi
  if [ -z "$fqdn" ]; then
    log "skip server keystore normalization (node_fqdn/fqdn missing in $node_conf)"
    return 0
  fi

  if [ ! -f "$cert_dir/cert-metadata.sh" ]; then
    log "skip server keystore normalization (missing $cert_dir/cert-metadata.sh)"
    return 0
  fi

  # shellcheck disable=SC1090
  . "$cert_dir/cert-metadata.sh"
  cert_pass="${PASS:-atakatak}"
  alias="$fqdn"

  src_key="$files_dir/$fqdn.key"
  src_pem="$files_dir/$fqdn.pem"
  dst_p12="$files_dir/$fqdn.p12"
  dst_jks="$files_dir/$fqdn.jks"

  if [ ! -f "$src_key" ] || [ ! -f "$src_pem" ]; then
    log "skip server keystore normalization (missing $src_key or $src_pem)"
    return 0
  fi

  log "normalizing server keystores for $fqdn with canonical alias/storepass/keypass"

  tmpdir="$(mktemp -d)"
  cleanup_normalize_server_keystores() {
    local d="${tmpdir:-}"
    trap - RETURN
    [ -n "$d" ] && rm -rf "$d"
  }
  trap cleanup_normalize_server_keystores RETURN

  openssl pkcs12 -legacy -export \
    -in "$src_pem" \
    -inkey "$src_key" \
    -passin "pass:$cert_pass" \
    -out "$tmpdir/$fqdn.p12" \
    -name "$alias" \
    -passout "pass:$cert_pass"

  keytool -importkeystore \
    -noprompt \
    -srckeystore "$tmpdir/$fqdn.p12" \
    -srcstoretype PKCS12 \
    -srcstorepass "$cert_pass" \
    -srcalias "$alias" \
    -srckeypass "$cert_pass" \
    -destkeystore "$tmpdir/$fqdn.jks" \
    -deststoretype JKS \
    -deststorepass "$cert_pass" \
    -destkeypass "$cert_pass" \
    -destalias "$alias" >/dev/null

  tmppass="$(uuidgen | tr -d '-')"
  check_p12="$tmpdir/check.p12"

  keytool -importkeystore \
    -noprompt \
    -srckeystore "$tmpdir/$fqdn.p12" \
    -srcstoretype PKCS12 \
    -srcstorepass "$cert_pass" \
    -srcalias "$alias" \
    -srckeypass "$cert_pass" \
    -destkeystore "$check_p12" \
    -deststoretype PKCS12 \
    -deststorepass "$tmppass" \
    -destkeypass "$tmppass" >/dev/null

  install_keystore_file "$tmpdir/$fqdn.p12" "$dst_p12"
  install_keystore_file "$tmpdir/$fqdn.jks" "$dst_jks"

  log "server keystores normalized: $dst_p12 and $dst_jks"
}



restart_takserver_if_present() {
  local have_systemd=0

  if systemctl list-unit-files --type=service --no-pager | grep -q '^takserver\.service'; then
    have_systemd=1
  elif [ ! -x /etc/init.d/takserver ]; then
    log "takserver service not found; skip restart"
    return 0
  fi

  if [ "$have_systemd" -eq 1 ]; then
    log "stopping takserver before final start after taks apply"
    systemctl stop takserver || true
  else
    log "stopping takserver via /etc/init.d before final start after taks apply"
    service takserver stop || /etc/init.d/takserver stop || true
  fi

  sleep 2

  log "killing any leftover takserver child JVMs"
  pkill -9 -f 'takserver\.jar' || true
  pkill -9 -f 'takserver\.war' || true
  pkill -9 -f 'takserver-web\.war' || true
  pkill -9 -f 'TAKServer\.jar' || true
  pkill -9 -f 'takserver-pm\.jar' || true
  pkill -9 -f 'takserver-retention\.jar' || true
  pkill -9 -f 'tak\.server\.ServerConfiguration' || true

  sleep 2

  log "removing stale generated /opt/tak/TAKIgniteConfig.xml before final start"
  rm -f /opt/tak/TAKIgniteConfig.xml

  if [ "$have_systemd" -eq 1 ]; then
    log "starting takserver after taks apply"
    systemctl start takserver
  else
    log "starting takserver via /etc/init.d after taks apply"
    service takserver start || /etc/init.d/takserver start
  fi
}

install_base_files() {
  mkdir -p /etc/taks /etc/taks-bootstrap.d /etc/taks-bootstrap.d/config.d /etc/taks-bootstrap.d/secrets.d

  if [ -f "$BUNDLE_ROOT/config/unit.json" ]; then
    install -m 0644 "$BUNDLE_ROOT/config/unit.json" /etc/taks/unit.json
    log "installed /etc/taks/unit.json"
  fi

  if [ -d "$BUNDLE_ROOT/install/taks-bootstrap/config.d" ]; then
    find "$BUNDLE_ROOT/install/taks-bootstrap/config.d" -type f -name '*.conf' | while read -r src; do
      rel="${src#$BUNDLE_ROOT/install/taks-bootstrap/config.d/}"
      dst="/etc/taks-bootstrap.d/config.d/$rel"
      mkdir -p "$(dirname "$dst")"
      install -m 0600 "$src" "$dst"
    done
    log "installed /etc/taks-bootstrap.d/config.d overlays"
  fi

  if [ -d "$BUNDLE_ROOT/install/taks-bootstrap/secrets.d" ]; then
    find "$BUNDLE_ROOT/install/taks-bootstrap/secrets.d" -type f -name '*.conf' | while read -r src; do
      rel="${src#$BUNDLE_ROOT/install/taks-bootstrap/secrets.d/}"
      dst="/etc/taks-bootstrap.d/secrets.d/$rel"
      mkdir -p "$(dirname "$dst")"
      install -m 0600 "$src" "$dst"
    done
    log "installed /etc/taks-bootstrap.d/secrets.d overlays"
  fi
}

seed_bootstrap_branding() {
  local node_conf="/etc/taks-bootstrap.d/config.d/node.conf"
  local src_dir="$BUNDLE_ROOT/branding"
  local fqdn=""
  local unit_id=""
  local dst_dir=""

  if [ ! -d "$src_dir" ]; then
    log "skip bootstrap branding seed (missing $src_dir)"
    return 0
  fi

  if [ ! -f "$node_conf" ]; then
    log "skip bootstrap branding seed (missing $node_conf)"
    return 0
  fi

  fqdn="$(read_simple_kv "$node_conf" node_fqdn || true)"
  if [ -z "$fqdn" ]; then
    fqdn="$(read_simple_kv "$node_conf" fqdn || true)"
  fi
  if [ -z "$fqdn" ]; then
    log "skip bootstrap branding seed (node_fqdn/fqdn missing in $node_conf)"
    return 0
  fi

  unit_id="${fqdn%%.*}"
  if [ -z "$unit_id" ]; then
    log "skip bootstrap branding seed (failed to derive unit id from fqdn=$fqdn)"
    return 0
  fi

  dst_dir="/opt/taks-bootstrap/$unit_id/branding"
  mkdir -p "$dst_dir"

  local src_real=""
  local dst_real=""
  src_real="$(cd "$src_dir" && pwd -P)"
  dst_real="$(cd "$dst_dir" && pwd -P)"

  if [ "$src_real" = "$dst_real" ]; then
    log "bootstrap branding already materialized in $dst_dir; skip self-copy"
    return 0
  fi

  find "$dst_dir" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
  cp -a "$src_dir"/. "$dst_dir"/

  log "seeded bootstrap branding into $dst_dir"
}

install_bundled_tls_material() {
  local node_conf="/etc/taks-bootstrap.d/config.d/node.conf"
  local src_dir="$BUNDLE_ROOT/install/letsencrypt"
  local src_cert="$src_dir/fullchain.pem"
  local src_key="$src_dir/privkey.pem"
  local fqdn

  if [ ! -f "$node_conf" ]; then
    log "skip bundled TLS install (missing $node_conf)"
    return 0
  fi

  fqdn="$(read_simple_kv "$node_conf" node_fqdn || true)"
  if [ -z "$fqdn" ]; then
    fqdn="$(read_simple_kv "$node_conf" fqdn || true)"
  fi
  if [ -z "$fqdn" ]; then
    log "skip bundled TLS install (node_fqdn/fqdn missing in $node_conf)"
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

  if find /etc/taks-bootstrap.d/config.d /etc/taks-bootstrap.d/secrets.d -maxdepth 1 -type f -name '*.conf' 2>/dev/null | grep -q .; then
    systemctl enable --now taks-heartbeat.timer
    log "enabled taks-heartbeat.timer"
  else
    log "bootstrap conf/secrets missing, not enabling taks-heartbeat.timer"
  fi
}

main() {
  log_state "install/main" "Started"
  log_state "install_base_files" "Started"
  install_base_files
  log_state "install_base_files" "Succeeded"

  log_state "install_bundled_tls_material" "Started"
  install_bundled_tls_material
  log_state "install_bundled_tls_material" "Succeeded"

  log_state "seed_bootstrap_branding" "Started"
  seed_bootstrap_branding
  log_state "seed_bootstrap_branding" "Succeeded"

  log_state "install_heartbeat" "Started"
  install_heartbeat
  log_state "install_heartbeat" "Succeeded"

  run_step "os-tuning" "$BUNDLE_ROOT/install/os-tuning.sh"
  run_step "takserver" "$BUNDLE_ROOT/install/takserver.sh"
  run_step "tak-certs-config" "$BUNDLE_ROOT/install/tak-certs-config.sh"

  log_state "generate_tak_server_certs" "Started"
  generate_tak_server_certs
  log_state "generate_tak_server_certs" "Succeeded"

  log_state "normalize_server_keystores" "Started"
  normalize_server_keystores
  log_state "normalize_server_keystores" "Succeeded"

  run_step "tak-certs-layout" "$BUNDLE_ROOT/install/tak-certs-layout.sh"
  run_step "tak-coreconfig-render" "$BUNDLE_ROOT/install/tak-coreconfig-render.sh"

  log_state "restart_takserver_if_present" "Started"
  restart_takserver_if_present
  log_state "restart_takserver_if_present" "Succeeded"

  if [ -f "$BUNDLE_ROOT/install/taks.sh" ]; then
    log_state "taks/apply" "Started"
    if bash "$BUNDLE_ROOT/install/taks.sh"; then
      log "taks step completed"
      log_state "taks/apply" "Succeeded"
    else
      log "WARNING: taks step failed; continuing"
      log_state "taks/apply" "Failed"
    fi
  fi

  run_step "taks-node-health" "$BUNDLE_ROOT/install/taks-node-health.sh"

  log "install complete"
  log_state "install/main" "Succeeded"
}

main "$@"
