#!/usr/bin/env bash
set -euo pipefail

nginx_quarantine_conflicts(){
  local se="/etc/nginx/sites-enabled"
  local q="/etc/nginx/sites-disabled-quarantine"
  mkdir -p "$se" "$q"

  shopt -s nullglob
  for f in "$se"/*; do
    [[ -f "$f" || -L "$f" ]] || continue
    if grep -Eq "server_name\s+${FQDN}\b|listen\s+80\b|listen\s+443\b|default_server" "$f" 2>/dev/null; then
      log "Quarantining enabled vhost: $f"
      mv -f "$f" "$q/$(basename "$f").$(date +%Y%m%d-%H%M%S)"
    fi
  done
  shopt -u nullglob
}

ensure_webroot(){
  mkdir -p /var/www/html/.well-known/acme-challenge
  chown -R www-data:www-data /var/www/html
}

write_nginx_canonical(){
  local sa="/etc/nginx/sites-available"
  local se="/etc/nginx/sites-enabled"
  local name="orch-master"
  local conf="${sa}/${name}.conf"
  mkdir -p "$sa" "$se"

  local tmp; tmp="$(mktemp)"
  cat >"$tmp" <<CONF
# Canonical orchestrator vhost for ${FQDN}
# 80  : ACME only + redirect to 443
# 443 : UI/API (reverse proxy will be added later)

server {
  listen 80;
  server_name ${FQDN};

  location /.well-known/acme-challenge/ {
    root /var/www/html;
    try_files \$uri =404;
  }

  location / {
    return 301 https://\$host\$request_uri;
  }
}

server {
  listen 443 ssl http2;
  server_name ${FQDN};

  ssl_certificate     /etc/letsencrypt/live/${FQDN}/fullchain.pem;
  ssl_certificate_key /etc/letsencrypt/live/${FQDN}/privkey.pem;

  location /orch/hello {
    # receive node call-home POSTs (best-effort)
    access_log /var/log/tak-orch/hello.log combined;
    error_log  /var/log/tak-orch/hello.error.log;

    # also dump request body into a file (requires ngx_http_lua_module normally; so we keep it simple)
    # NGINX cannot natively log request bodies without extras; we at least log metadata.
    return 200 "ok\n";
  }

  location / {
    return 200 "orchestrator: nginx up (API/UI pending)\n";
    add_header Content-Type text/plain;
  }
}
CONF

  if [[ -f "$conf" ]] && cmp -s "$tmp" "$conf"; then
    rm -f "$tmp"
    log "NGINX canonical config unchanged."
  else
    if [[ -f "$conf" ]]; then
      mkdir -p /etc/nginx/backup
      cp -a "$conf" "/etc/nginx/backup/$(basename "$conf").bak.$(date +%Y%m%d-%H%M%S)"
    fi
    mv -f "$tmp" "$conf"
    log "Wrote NGINX canonical config: $conf"
  fi

  ln -sf "$conf" "$se/${name}.conf"
}

le_cert_obtain(){
  if [[ -f "/etc/letsencrypt/live/${FQDN}/fullchain.pem" ]]; then
    log "LE cert already present for ${FQDN}"
    return 0
  fi

  nginx -t || die "nginx config invalid before certbot"
  systemctl reload nginx

  log "Requesting LE cert for ${FQDN}"
  certbot certonly --nginx \
    -d "${FQDN}" \
    --non-interactive --agree-tos \
    -m "${LE_EMAIL}" || die "certbot failed (DNS/SG/80 reachability?)"
}

nginx_reload_safe(){
  nginx -t || die "nginx config invalid"
  systemctl reload nginx
}
