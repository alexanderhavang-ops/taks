#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/install/devops-mtls"
NODE_CONF="/etc/taks-bootstrap.d/config.d/node.conf"
DEST="/etc/taks-devops/tls"

[ "$(id -u)" -eq 0 ] || { echo "DevOps mTLS install requires root" >&2; exit 1; }
for f in ca.crt node.crt node.key; do
  [ -s "$SRC/$f" ] || { echo "Missing bundled DevOps TLS $f" >&2; exit 1; }
done
[ -f "$NODE_CONF" ] || { echo "Missing node.conf" >&2; exit 1; }
fqdn="$(sed -n 's/^[[:space:]]*fqdn[[:space:]]*=[[:space:]]*//p' "$NODE_CONF" | head -n 1 | tr -d '\r')"
[[ "$fqdn" =~ ^[a-zA-Z0-9][a-zA-Z0-9.-]*[a-zA-Z0-9]$ ]] || { echo "Invalid node FQDN" >&2; exit 1; }

openssl verify -CAfile "$SRC/ca.crt" "$SRC/node.crt" >/dev/null
openssl x509 -in "$SRC/node.crt" -noout -checkend 604800 >/dev/null
openssl x509 -in "$SRC/node.crt" -noout -ext subjectAltName | grep -Fq "DNS:devops.$fqdn"
cert_pub="$(openssl x509 -in "$SRC/node.crt" -pubkey -noout)"
key_pub="$(openssl pkey -in "$SRC/node.key" -pubout)"
[ "$cert_pub" = "$key_pub" ] || { echo "DevOps TLS key mismatch" >&2; exit 1; }

install -d -m 0700 "$DEST"
install -m 0644 "$SRC/ca.crt" "$DEST/ca.crt"
install -m 0644 "$SRC/node.crt" "$DEST/node.crt"
install -m 0600 "$SRC/node.key" "$DEST/node.key"

# A distinct SNI vhost on the existing HTTPS listener, not a second service.
site="/etc/nginx/sites-available/taks-devops-mtls.conf"
enabled="/etc/nginx/sites-enabled/taks-devops-mtls.conf"
install -d -m 0755 /etc/nginx/sites-available /etc/nginx/sites-enabled
tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT
cat >"$tmp" <<EOF
server {
    listen 443 ssl;
    server_name devops.$fqdn;
    ssl_certificate $DEST/node.crt;
    ssl_certificate_key $DEST/node.key;
    ssl_client_certificate $DEST/ca.crt;
    ssl_verify_client on;
    ssl_verify_depth 1;
    ssl_protocols TLSv1.2 TLSv1.3;
    client_max_body_size 64k;
    location = /api/orchestrator/mcp/devops {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host \$host;
        proxy_set_header X-Forwarded-Proto https;
        proxy_connect_timeout 5s;
        proxy_read_timeout 25s;
    }
    location / { return 404; }
}
EOF
install -m 0644 "$tmp" "$site"
ln -sfn "$site" "$enabled"
nginx -t
systemctl reload nginx
echo "Installed node DevOps mTLS endpoint: devops.$fqdn"
