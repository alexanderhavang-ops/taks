#!/usr/bin/env bash
set -euo pipefail

# Online (LE) outputs
le_cert_paths_set(){
  TLS_CERT="/etc/letsencrypt/live/${FQDN}/fullchain.pem"
  TLS_KEY="/etc/letsencrypt/live/${FQDN}/privkey.pem"
}

# Offline inputs (operator-provided)
offline_cert_paths_set(){
  TLS_CERT="${TLS_CERT:-/etc/tak/certs/public/fullchain.pem}"
  TLS_KEY="${TLS_KEY:-/etc/tak/certs/public/privkey.pem}"
}

ensure_webroot(){
  mkdir -p /var/www/html/.well-known/acme-challenge
  chown -R www-data:www-data /var/www/html || true
}

le_cert_obtain(){
  le_cert_paths_set

  if [[ -f "$TLS_CERT" && -f "$TLS_KEY" ]]; then
    log "LE cert already present for ${FQDN}"
    return 0
  fi

  command -v certbot >/dev/null 2>&1 || die "certbot not installed (online mode requires it)"
  nginx -t || die "nginx config invalid before certbot"
  systemctl reload nginx

  log "Requesting LE cert for ${FQDN}"
  certbot certonly --nginx \
    -d "${FQDN}" \
    --non-interactive --agree-tos \
    -m "${LE_EMAIL}" || die "certbot failed (DNS/SG/80 reachability?)"

  [[ -f "$TLS_CERT" && -f "$TLS_KEY" ]] || die "LE certbot completed but cert files missing"
}

certs_prepare(){
  ensure_webroot

  case "$INSTALL_MODE" in
    online)
      le_cert_obtain
      ;;
    offline)
      offline_cert_paths_set
      [[ -f "$TLS_CERT" ]] || die "offline mode: missing TLS_CERT ($TLS_CERT)"
      [[ -f "$TLS_KEY"  ]] || die "offline mode: missing TLS_KEY ($TLS_KEY)"
      ;;
    *)
      die "unknown INSTALL_MODE: $INSTALL_MODE"
      ;;
  esac
}
