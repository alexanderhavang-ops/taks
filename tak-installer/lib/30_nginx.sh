#!/usr/bin/env bash
set -euo pipefail

nginx_quarantine_conflicts(){
  local se="/etc/nginx/sites-enabled"
  local q="/etc/nginx/sites-disabled-quarantine"
  mkdir -p "$se" "$q"

  shopt -s nullglob
  for f in "$se"/*; do
    [[ -f "$f" || -L "$f" ]] || continue
    if grep -Eq "server_name\s+${FQDN}\b|listen\s+80\b|listen\s+8446\b|listen\s+443\b|default_server" "$f" 2>/dev/null; then
      log "Quarantining enabled vhost: $f"
      mv -f "$f" "$q/$(basename "$f").$(date +%Y%m%d-%H%M%S)"
    fi
  done
  shopt -u nullglob
}

write_nginx_taknode_canonical(){
  local sa="/etc/nginx/sites-available"
  local se="/etc/nginx/sites-enabled"
  local name="taknode"
  local conf="${sa}/${name}.conf"

  mkdir -p "$sa" "$se"
  mkdir -p /var/www/html/.well-known/acme-challenge

  local tmp; tmp="$(mktemp)"
  cat >"$tmp" <<CONF
# Canonical TAK node NGINX for ${FQDN}
#
# 80   : ACME only + redirect all else to 8446
# 8446 : public entrypoint -> proxies to TAK https connector on 127.0.0.1:8447
#
# NOTE: TLS cert paths are placeholders until LE/internal cert is installed.

server {
  listen 80;
  server_name ${FQDN};

  location /.well-known/acme-challenge/ {
    root /var/www/html;
    try_files \$uri =404;
  }

  location / {
    return 301 https://\$host:${PUBLIC_PORT_ENROLL}\$request_uri;
  }
}

server {
  listen ${PUBLIC_PORT_ENROLL} ssl http2;
  server_name ${FQDN};

  # Placeholder cert paths (next step will install real certs)
  ssl_certificate     ${TLS_CERT};
  ssl_certificate_key ${TLS_KEY};

  location /Marti/ {
    proxy_pass https://127.0.0.1:8447/Marti/;
    proxy_set_header Host \$host;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-Port ${PUBLIC_PORT_ENROLL};
    proxy_ssl_verify off;
  }

  location /WebTak/ {
    proxy_pass https://127.0.0.1:8447/WebTak/;
    proxy_set_header Host \$host;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-Port ${PUBLIC_PORT_ENROLL};
    proxy_ssl_verify off;
  }

  location /oauth/ {
    proxy_pass https://127.0.0.1:8447/oauth/;
    proxy_set_header Host \$host;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-Port ${PUBLIC_PORT_ENROLL};
    proxy_ssl_verify off;
  }

  location / {
    return 404;
  }
}
CONF

  if [[ -f "$conf" ]] && cmp -s "$tmp" "$conf"; then
    rm -f "$tmp"
    log "NGINX canonical taknode config unchanged."
  else
    if [[ -f "$conf" ]]; then
      mkdir -p /etc/nginx/backup
      cp -a "$conf" "/etc/nginx/backup/$(basename "$conf").bak.$(date +%Y%m%d-%H%M%S)"
    fi
    mv -f "$tmp" "$conf"
    log "Wrote NGINX taknode config: $conf"
  fi

  ln -sf "$conf" "$se/${name}.conf"
}

nginx_reload_safe(){
  nginx -t || die "nginx config invalid"
  systemctl enable --now nginx
  systemctl reload nginx
}
