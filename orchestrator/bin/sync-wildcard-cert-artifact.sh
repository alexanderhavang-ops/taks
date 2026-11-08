#!/usr/bin/env bash
# Run as root via Certbot deploy-hook and once after installation.
set -euo pipefail

lineage=/etc/letsencrypt/live/aws.tak-hv-sandbox.se
dest=/opt/tak-orch/state/artifacts/letsencrypt/aws.tak-hv-sandbox.se

if [[ -n "${RENEWED_LINEAGE:-}" ]]; then
  [[ "$(readlink -f "$RENEWED_LINEAGE")" == "$(readlink -f "$lineage")" ]] || exit 0
fi
[[ "$(id -u)" == 0 ]] || { echo "root required" >&2; exit 1; }
[[ -d "$dest" && -f "$dest/fullchain.pem" && -f "$dest/privkey.pem" ]] ||
  { echo "Expected TAKS artifact directory missing: $dest" >&2; exit 1; }

openssl x509 -in "$lineage/fullchain.pem" -noout -checkend 604800
cert_pub="$(openssl x509 -in "$lineage/fullchain.pem" -pubkey -noout | openssl sha256)"
key_pub="$(openssl pkey -in "$lineage/privkey.pem" -pubout | openssl sha256)"
[[ "$cert_pub" == "$key_pub" ]] || { echo "Certbot key mismatch" >&2; exit 1; }
openssl x509 -in "$lineage/fullchain.pem" -noout -ext subjectAltName |
  grep -Fq 'DNS:*.aws.tak-hv-sandbox.se' ||
  { echo "Expected wildcard SAN missing" >&2; exit 1; }

group="$(stat -c '%g' "$dest/privkey.pem")"
temp="$(mktemp -d "${dest}.staging.XXXXXXXX")"
trap 'rm -rf "$temp"' EXIT
install -o ubuntu -g "$group" -m 0640 "$lineage/fullchain.pem" "$temp/fullchain.pem"
install -o ubuntu -g "$group" -m 0640 "$lineage/privkey.pem" "$temp/privkey.pem"

# Bundle builder verifies the keypair and expiry before publication.
install -o ubuntu -g "$group" -m 0640 "$temp/fullchain.pem" "$dest/fullchain.pem"
install -o ubuntu -g "$group" -m 0640 "$temp/privkey.pem" "$dest/privkey.pem"
openssl x509 -in "$dest/fullchain.pem" -noout -checkend 604800
echo "Updated TAKS wildcard artifact from Certbot live lineage"
