#!/usr/bin/env bash
set -euo pipefail

ORCH_CONF_FILE="${ORCH_CONF_FILE:-/etc/taks/tak_orch.conf}"

_conf_py(){
  local expr="${1:?missing python expr}"
  python3 - "$ORCH_CONF_FILE" "$expr" <<'PY'
from pathlib import Path
import sys
try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

conf_path = Path(sys.argv[1])
expr = sys.argv[2]

if not conf_path.exists():
    raise SystemExit(f"missing config file: {conf_path}")

raw = tomllib.loads(conf_path.read_text(encoding="utf-8"))

def req(section, key):
    sec = raw.get(section)
    if not isinstance(sec, dict):
        raise SystemExit(f"missing section: {section}")
    val = sec.get(key)
    if not isinstance(val, str) or not val.strip():
        raise SystemExit(f"missing required string: {section}.{key}")
    return val.strip()

mapping = {
    "identity.orchestrator_fqdn": ("identity", "orchestrator_fqdn"),
    "letsencrypt.email": ("letsencrypt", "email"),
    "letsencrypt.mode": ("letsencrypt", "mode"),
    "letsencrypt.wildcard_zone": ("letsencrypt", "wildcard_zone"),
    "letsencrypt.artifact_cert_dir": ("letsencrypt", "artifact_cert_dir"),
}

if expr not in mapping:
    raise SystemExit(f"unsupported expr: {expr}")

section, key = mapping[expr]
print(req(section, key))
PY
}

ensure_webroot(){
  mkdir -p /var/www/html/.well-known/acme-challenge
  chown -R www-data:www-data /var/www/html || true
}

le_mode(){ _conf_py "letsencrypt.mode"; }
le_domain(){ _conf_py "letsencrypt.wildcard_zone"; }
le_wildcard(){ local d; d="$(le_domain)"; printf '*.%s' "${d}"; }

public_cert_path(){ printf '%s' "/etc/letsencrypt/live/${FQDN}/fullchain.pem"; }
public_key_path(){ printf '%s' "/etc/letsencrypt/live/${FQDN}/privkey.pem"; }

artifact_source_cert_path(){ local d; d="$(le_domain)"; printf '%s' "/etc/letsencrypt/live/${d}/fullchain.pem"; }
artifact_source_key_path(){ local d; d="$(le_domain)"; printf '%s' "/etc/letsencrypt/live/${d}/privkey.pem"; }
artifact_tls_dir(){ _conf_py "letsencrypt.artifact_cert_dir"; }

sync_le_cert_to_artifacts(){
  local src_cert src_key dst_dir
  src_cert="$(artifact_source_cert_path)"
  src_key="$(artifact_source_key_path)"
  dst_dir="$(artifact_tls_dir)"

  if [[ ! -f "$src_cert" || ! -f "$src_key" ]]; then
    log "No LE cert material to sync into artifacts for $(le_domain)"
    return 0
  fi

  install -d -m 0750 -o ubuntu -g taks-state "$dst_dir"
  install -m 0640 -o ubuntu -g taks-state "$src_cert" "$dst_dir/fullchain.pem"
  install -m 0640 -o ubuntu -g taks-state "$src_key" "$dst_dir/privkey.pem"

  log "Synced LE cert material into $dst_dir"
}

choose_tls_paths(){
  local le_cert le_key
  le_cert="$(public_cert_path)"
  le_key="$(public_key_path)"

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

  client_max_body_size 2048m;

  ssl_certificate     ${TLS_CERT};
  ssl_certificate_key ${TLS_KEY};

  location /healthz {
    add_header Content-Type text/plain;
    return 200 "ok\n";
  }

  location ^~ /api/v1/nodes/ {
    access_log /var/log/nginx/nodes_access.log node_auth;
    proxy_http_version 1.1;
    proxy_set_header Host              \$host;
    proxy_set_header X-Real-IP         \$remote_addr;
    proxy_set_header X-Forwarded-For   \$proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto \$scheme;
    proxy_pass http://127.0.0.1:8090;
    proxy_read_timeout  60s;
    proxy_send_timeout  60s;
  }

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
    if grep -Eq "listen[[:space:]]+80\\b|listen[[:space:]]+443\\b|default_server|server_name[[:space:]]+${FQDN}\\b" "$f" 2>/dev/null; then
      log "Quarantining enabled vhost: $f"
      mv -f "$f" "$q/$(basename "$f").$(date +%Y%m%d-%H%M%S)"
    fi
  done
  shopt -u nullglob
}

le_cert_obtain_dns_route53(){
  local cert_domain wildcard
  cert_domain="$(le_domain)"
  wildcard="$(le_wildcard)"

  [[ -n "${LE_EMAIL:-}" ]] || die "LE_EMAIL is required for dns-route53 mode"

  local le_cert="/etc/letsencrypt/live/${cert_domain}/fullchain.pem"
  local le_key="/etc/letsencrypt/live/${cert_domain}/privkey.pem"

  if [[ -f "$le_cert" && -f "$le_key" ]]; then
    log "LE cert already present for ${cert_domain}"
    return 0
  fi

  log "Requesting LE cert via Route53 DNS-01 for ${cert_domain}${wildcard:+ and ${wildcard}}"

  certbot certonly \
    --dns-route53 \
    --non-interactive \
    --agree-tos \
    -m "${LE_EMAIL}" \
    -d "${cert_domain}" \
    -d "${wildcard}" || die "certbot dns-route53 failed"

  [[ -f "$le_cert" && -f "$le_key" ]] || die "LE cert files missing after dns-route53 certbot"
}

le_cert_obtain_http01(){
  local le_cert le_key
  le_cert="$(public_cert_path)"
  le_key="$(public_key_path)"

  if [[ -f "$le_cert" && -f "$le_key" ]]; then
    log "LE cert already present for ${FQDN}"
    return 0
  fi

  log "Requesting LE cert for ${FQDN} (HTTP-01 via nginx on port 80)"

  local my_ip=""
  my_ip="$(curl -fsS https://ifconfig.me 2>/dev/null || true)"
  if [[ -z "$my_ip" ]]; then
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
    --non-interactive \
    --agree-tos \
    -m "${LE_EMAIL}" || die "certbot failed (DNS/SG/80 reachability?)"

  [[ -f "$le_cert" && -f "$le_key" ]] || die "LE cert files missing after certbot"
}

le_cert_obtain(){
  local mode
  mode="$(le_mode)"

  case "$mode" in
    dns-route53|dns_route53|wildcard_dns_01|WILDCARD_DNS_01)
      le_cert_obtain_dns_route53
      sync_le_cert_to_artifacts
      ;;
    http-01|http01|HTTP_01)
      le_cert_obtain_http01
      ;;
    *)
      die "unsupported letsencrypt.mode: $mode"
      ;;
  esac
}

nginx_reload_safe(){
  nginx -t || die "nginx config invalid"
  systemctl reload nginx
}
