#!/usr/bin/env bash
set -euo pipefail

FQDN="${FQDN:-}"
if [[ -z "${FQDN}" ]]; then
  echo "ERROR: set FQDN env var (e.g. FQDN=46hvbat.tak-hv-sandbox.se)"
  exit 2
fi

ok()  { printf "OK   %s\n" "$*"; }
bad() { printf "FAIL %s\n" "$*"; exit 1; }

echo "== TAKS self-test =="
echo "FQDN=${FQDN}"
echo

# Local process/service checks
systemctl is-active nginx >/dev/null || bad "nginx not active"
ok "nginx active"

systemctl is-active takctl-web.service >/dev/null || bad "takctl-web.service not active"
ok "takctl-web active"

# Local takctl health
curl -fsS "http://127.0.0.1:8080/api/health" >/dev/null || bad "loopback takctl /api/health failed"
ok "takctl loopback health"

# Public takctl (443) – expects LE-valid cert, no -k
curl -fsS "https://${FQDN}/takctl/api/health" >/dev/null || bad "public takctl health failed (443)"
ok "takctl public health (443)"

# Port 80: root should redirect; acme-challenge path should exist (404 is fine, but must not be connection failure)
code="$(curl -sS -o /dev/null -w '%{http_code}' "http://${FQDN}/")" || bad "http/80 root request failed"
[[ "${code}" =~ ^30[12]$ ]] || bad "http/80 expected redirect, got ${code}"
ok "http/80 redirects (${code})"

code="$(curl -sS -o /dev/null -w '%{http_code}' "http://${FQDN}/.well-known/acme-challenge/this-should-404")" || bad "http/80 acme path request failed"
[[ "${code}" == "404" ]] || bad "http/80 acme expected 404, got ${code}"
ok "http/80 acme location reachable (${code})"

# Port 8446: front door reachable, and /Marti/ answers something (200/30x/401 are all acceptable "alive" signals)
code="$(curl -sS -o /dev/null -w '%{http_code}' "https://${FQDN}:8446/")" || bad "https/8446 root request failed"
[[ "${code}" =~ ^30[12]$ ]] || bad "https/8446 expected redirect at /, got ${code}"
ok "https/8446 redirects root (${code})"

code="$(curl -sS -o /dev/null -w '%{http_code}' "https://${FQDN}:8446/Marti/")" || bad "https/8446 /Marti/ request failed"
# allow 200, 30x, 401, 403
[[ "${code}" == "200" || "${code}" =~ ^30[12]$ || "${code}" == "401" || "${code}" == "403" ]] || bad "https/8446 /Marti/ unexpected ${code}"
ok "https/8446 /Marti/ alive (${code})"

echo
echo "ALL GREEN"
