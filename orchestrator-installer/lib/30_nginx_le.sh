#!/usr/bin/env bash
set -euo pipefail

ensure_webroot(){
  mkdir -p /var/www/html/.well-known/acme-challenge
  chown -R www-data:www-data /var/www/html || true
}

choose_tls_paths(){
  local le_cert="/etc/letsencrypt/live/${FQDN}/fullchain.pem"
  local le_key="/etc/letsencrypt/live/${FQDN}/privkey.pem"

  if [[ -f "$le_cert" && -f "$le_key" ]]; then
    TLS_CERT="$le_cert"
    TLS_KEY="$le_key"
  else
    TLS_CERT="/etc/ssl/certs/ssl-cert-snakeoil.pem"
    TLS_KEY="/etc/ssl/private/ssl-cert-snakeoil.key"
  fi
}

write_nginx_canonical(){
  choose_tls_paths
  ensure_webroot

  local conf="/etc/nginx/sites-available/orch-master.conf"
  install -d -m 0755 /etc/nginx/sites-available /etc/nginx/sites-enabled

  cat > "$conf" <<NGINX
server {
  listen 80;
  server_name ${FQDN};

  location ^~ /.well-known/acme-challenge/ {
    root /var/www/html;
    default_type "text/plain";
    try_files \$uri =404;
  }

  location / {
    return 301 https://\$host\$request_uri;
  }
}

server {
  listen 443 ssl http2;
  server_name ${FQDN};

  ssl_certificate     ${TLS_CERT};
  ssl_certificate_key ${TLS_KEY};

  # simple endpoints for node call-home + health
  location /healthz {
    add_header Content-Type text/plain;
    return 200 "ok\n";
  }

  location /orch/hello {
    access_log /var/log/tak-orch/hello.log combined;
    error_log  /var/log/tak-orch/hello.error.log;
    add_header Content-Type text/plain;
    return 200 "ok\n";
  }

  location / {
    return 200 "orchestrator: nginx up (API/UI pending)\n";
  }
}
NGINX

  ln -sf "$conf" /etc/nginx/sites-enabled/orch-master.conf
}

nginx_quarantine_conflicts(){
  local se="/etc/nginx/sites-enabled"
  local q="/etc/nginx/sites-disabled-quarantine"
  mkdir -p "$se" "$q"

  shopt -s nullglob
  for f in "$se"/*; do
    [[ -f "$f" || -L "$f" ]] || continue
    if [[ "$(basename "$f")" == "orch-master.conf" ]]; then
      continue
    fi
    # quarantine anything that could conflict with our ports
    if grep -Eq "listen\s+80\b|listen\s+443\b|default_server|server_name\s+${FQDN}\b" "$f" 2>/dev/null; then
      log "Quarantining enabled vhost: $f"
      mv -f "$f" "$q/$(basename "$f").$(date +%Y%m%d-%H%M%S)"
    fi
  done
  shopt -u nullglob
}

le_cert_obtain(){
  local le_cert="/etc/letsencrypt/live/${FQDN}/fullchain.pem"
  local le_key="/etc/letsencrypt/live/${FQDN}/privkey.pem"

  if [[ -f "$le_cert" && -f "$le_key" ]]; then
    log "LE cert already present for ${FQDN}"
    return 0
  fi

  log "Requesting LE cert for ${FQDN} (HTTP-01 via nginx on port 80)"
  certbot certonly --nginx \
    -d "${FQDN}" \
    --non-interactive --agree-tos \
    -m "${LE_EMAIL}" || die "certbot failed (DNS/SG/80 reachability?)"

  [[ -f "$le_cert" && -f "$le_key" ]] || die "LE cert files missing after certbot"
}


nginx_reload_safe(){
  nginx -t || die "nginx config invalid"
  systemctl enable --now nginx
  systemctl reload nginx
}
