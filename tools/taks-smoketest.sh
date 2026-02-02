#!/usr/bin/env bash
set -euo pipefail

FQDN="${FQDN:-}"
if [[ -z "${FQDN}" ]]; then
  echo "ERROR: set FQDN env (e.g. FQDN=46hvbat.tak-hv-sandbox.se)" >&2
  exit 2
fi

echo "=== takctl-web loopback ==="
curl -fsS http://127.0.0.1:8080/api/health | jq -c .
echo

echo "=== nginx 443 (takctl) ==="
curl -fsS "https://${FQDN}/takctl/api/health" | jq -c .
echo

echo "=== nginx 80 (acme redirect sanity) ==="
# Expect 301/308 to https; just show status+location
curl -sSI "http://${FQDN}/.well-known/acme-challenge/ping" | awk 'NR==1||tolower($1)=="location:"'
echo

echo "=== nginx 8446 (front door) ==="
# This is TAK's public edge; these endpoints may return 302/401/403 depending on server config.
# We just prove TLS works and that we get an HTTP response from nginx.
curl -skSI "https://${FQDN}:8446/Marti/" | awk 'NR==1||tolower($1)=="server:"||tolower($1)=="location:"'
echo

echo "OK"
