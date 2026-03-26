#!/usr/bin/env bash
set -euo pipefail

node_cert_model(){
  printf '%s' "${TAKS_NODE_CERT_MODEL:-HTTP_01}"
}

le_cert_paths_set(){
  TLS_CERT="/etc/letsencrypt/live/${FQDN}/fullchain.pem"
  TLS_KEY="/etc/letsencrypt/live/${FQDN}/privkey.pem"
}

offline_cert_paths_set(){
  TLS_CERT="${TLS_CERT:-/etc/tak/certs/public/fullchain.pem}"
  TLS_KEY="${TLS_KEY:-/etc/tak/certs/public/privkey.pem}"
}

wildcard_bundle_cert_paths_set(){
  BUNDLE_TLS_CERT="${BUNDLE_TLS_CERT:-/opt/tak/install/letsencrypt/fullchain.pem}"
  BUNDLE_TLS_KEY="${BUNDLE_TLS_KEY:-/opt/tak/install/letsencrypt/privkey.pem}"
}

ensure_webroot(){
  mkdir -p /var/www/html/.well-known/acme-challenge
  chown -R www-data:www-data /var/www/html || true
}

ensure_live_dir(){
  local live_dir
  live_dir="/etc/letsencrypt/live/${FQDN}"
  mkdir -p "$live_dir"
  chmod 0755 "$live_dir"
}

install_wildcard_cert_to_live_path(){
  le_cert_paths_set
  wildcard_bundle_cert_paths_set
  ensure_live_dir

  [[ -f "$BUNDLE_TLS_CERT" ]] || die "wildcard mode: missing bundle cert ($BUNDLE_TLS_CERT)"
  [[ -f "$BUNDLE_TLS_KEY"  ]] || die "wildcard mode: missing bundle key ($BUNDLE_TLS_KEY)"

  install -m 0644 "$BUNDLE_TLS_CERT" "$TLS_CERT"
  install -m 0600 "$BUNDLE_TLS_KEY" "$TLS_KEY"

  [[ -f "$TLS_CERT" ]] || die "wildcard mode: failed to install TLS_CERT ($TLS_CERT)"
  [[ -f "$TLS_KEY"  ]] || die "wildcard mode: failed to install TLS_KEY ($TLS_KEY)"

  log "installed wildcard TLS material for ${FQDN} into /etc/letsencrypt/live/${FQDN}"
}

le_cert_obtain_http01(){
  le_cert_paths_set

  if [[ -f "$TLS_CERT" && -f "$TLS_KEY" ]]; then
    log "LE cert already present for ${FQDN}"
    return 0
  fi

  command -v certbot >/dev/null 2>&1 || die "certbot not installed (HTTP_01 mode requires it)"
  [[ -n "${LE_EMAIL:-}" ]] || die "HTTP_01 mode requires LE_EMAIL"

  nginx -t || die "nginx config invalid before certbot"
  systemctl enable --now nginx
  systemctl reload nginx

  log "Requesting LE cert for ${FQDN} via HTTP-01 (port 80)"
  certbot certonly --nginx \
    -d "${FQDN}" \
    --non-interactive --agree-tos \
    -m "${LE_EMAIL}" \
    || die "certbot failed (DNS/SG/80 reachability?)"

  [[ -f "$TLS_CERT" ]] || die "LE certbot completed but missing TLS_CERT ($TLS_CERT)"
  [[ -f "$TLS_KEY"  ]] || die "LE certbot completed but missing TLS_KEY ($TLS_KEY)"
}

certs_prepare(){
  ensure_webroot

  case "$(node_cert_model)" in
    HTTP_01)
      case "$INSTALL_MODE" in
        online)
          le_cert_obtain_http01
          ;;
        offline)
          offline_cert_paths_set
          [[ -f "$TLS_CERT" ]] || die "offline+HTTP_01 mode: missing TLS_CERT ($TLS_CERT)"
          [[ -f "$TLS_KEY"  ]] || die "offline+HTTP_01 mode: missing TLS_KEY ($TLS_KEY)"
          ;;
        *)
          die "unknown INSTALL_MODE: $INSTALL_MODE"
          ;;
      esac
      ;;
    WILDCARD_DNS_01)
      install_wildcard_cert_to_live_path
      ;;
    *)
      die "unknown TAKS_NODE_CERT_MODEL: $(node_cert_model)"
      ;;
  esac
}
