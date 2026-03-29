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
  local node_env="/etc/taks-bootstrap.d/node.env"
  local cert_dir="/opt/tak/certs"

  if [ ! -d "$cert_dir" ]; then
    log "skip cert generation (missing $cert_dir)"
    return 0
  fi

  if [ ! -f "$node_env" ]; then
    log "skip cert generation (missing $node_env)"
    return 0
  fi

  # shellcheck disable=SC1090
  . "$node_env"

  local fqdn="${TAKS_NODE_FQDN:-${TAKS_FQDN:-}}"
  if [ -z "$fqdn" ]; then
    log "skip cert generation (TAKS_NODE_FQDN/TAKS_FQDN missing)"
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

restart_takserver_if_present() {
  if systemctl list-unit-files --type=service --no-pager | grep -q '^takserver\.service'; then
    log "restarting takserver after cert/coreconfig render"
    systemctl restart takserver || systemctl start takserver || true
    return 0
  fi

  if [ -x /etc/init.d/takserver ]; then
    log "restarting takserver via /etc/init.d after cert/coreconfig render"
    service takserver restart || service takserver start || /etc/init.d/takserver restart || /etc/init.d/takserver start || true
    return 0
  fi

  log "takserver service not found; skip restart"
}

install_base_files() {
  mkdir -p /etc/taks /etc/taks-bootstrap.d

  if [ -f "$BUNDLE_ROOT/config/unit.json" ]; then
    install -m 0644 "$BUNDLE_ROOT/config/unit.json" /etc/taks/unit.json
    log "installed /etc/taks/unit.json"
  fi

  if [ -f "$BUNDLE_ROOT/install/node.env" ]; then
    install -m 0600 "$BUNDLE_ROOT/install/node.env" /etc/taks-bootstrap.d/node.env
    log "installed /etc/taks-bootstrap.d/node.env"
  fi
}

install_bundled_tls_material() {
  local node_env="/etc/taks-bootstrap.d/node.env"
  local src_dir="$BUNDLE_ROOT/install/letsencrypt"
  local src_cert="$src_dir/fullchain.pem"
  local src_key="$src_dir/privkey.pem"

  if [ ! -f "$node_env" ]; then
    log "skip bundled TLS install (missing /etc/taks-bootstrap.d/node.env)"
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

  if [ -f /etc/taks-bootstrap.d/node.env ]; then
    systemctl enable --now taks-heartbeat.timer
    log "enabled taks-heartbeat.timer"
  else
    log "bootstrap node.env missing, not enabling taks-heartbeat.timer"
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

  run_step "tak-certs-config" "$BUNDLE_ROOT/install/tak-certs-config.sh"
  generate_tak_server_certs
  run_step "tak-certs-layout" "$BUNDLE_ROOT/install/tak-certs-layout.sh"
  run_step "tak-coreconfig-render" "$BUNDLE_ROOT/install/tak-coreconfig-render.sh"
  restart_takserver_if_present

  log "install complete"
}

main "$@"
