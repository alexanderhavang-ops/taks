#!/usr/bin/env bash
set -euo pipefail

ensure_webroot(){
  # Canonical webroot for ACME HTTP-01
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
    # fallback until LE succeeds
    TLS_CERT="/etc/ssl/certs/ssl-cert-snakeoil.pem"
    TLS_KEY="/etc/ssl/private/ssl-cert-snakeoil.key"
  fi
}

write_nginx_canonical(){
  choose_tls_paths
  ensure_webroot

  local conf="/etc/nginx/sites-available/orch-master.conf"
  install -d -m 0755 /etc/nginx/sites-available /etc/nginx/sites-enabled

  # One canonical vhost:
  # - :80 serves ACME challenges + redirects everything else to https
  # - :443 terminates TLS and proxies to orchestrator backend on 127.0.0.1:8090
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

  # health lives at nginx level (useful even if backend is down)
  location /healthz {
    add_header Content-Type text/plain;
    return 200 "ok\n";
  }

  # Orchestrator backend (FastAPI)
  location / {
    proxy_http_version 1.1;

    proxy_set_header Host              \$host;
    proxy_set_header X-Real-IP         \$remote_addr;
    proxy_set_header X-Forwarded-For   \$proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto \$scheme;

    proxy_pass http://127.0.0.1:8090;

    proxy_read_timeout  60s;
    proxy_send_timeout  60s;
  }
}
NGINX

  ln -sfn "$conf" /etc/nginx/sites-enabled/orch-master.conf
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
    # quarantine anything that could conflict with our ports or name
    if grep -Eq "listen[[:space:]]+80\\b|listen[[:space:]]+443\\b|default_server|server_name[[:space:]]+${FQDN}\\b" "$f" 2>/dev/null; then
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

  # Preflight: for HTTP-01 to work, FQDN must resolve to THIS host (otherwise LE hits someone else).
  local my_ip=""
  my_ip="$(curl -fsS https://ifconfig.me 2>/dev/null || true)"
  if [[ -z "$my_ip" ]]; then
    # fallback (sometimes blocked); best-effort only
    my_ip="$(curl -fsS https://api.ipify.org 2>/dev/null || true)"
  fi

  local a_records=""
  a_records="$(dig +short "${FQDN}" A 2>/dev/null | tr '\n' ' ' | xargs || true)"

  if [[ -n "$my_ip" ]]; then
    if [[ -z "$a_records" || " $a_records " != *" $my_ip "* ]]; then
      die "LE HTTP-01 preflight failed: ${FQDN} does not resolve to this host.
  this host public IP: ${my_ip}
  ${FQDN} A records:   ${a_records:-<none>}
Fix DNS (or use correct FQDN) before running certbot."
    fi
  else
    log "WARN: could not determine public IP (ifconfig.me/ipify). Skipping DNS preflight for ${FQDN}."
  fi

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

