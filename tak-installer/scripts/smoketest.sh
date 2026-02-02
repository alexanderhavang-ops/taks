#!/usr/bin/env bash
set -euo pipefail

FQDN="${FQDN:-}"
if [[ -z "${FQDN}" ]]; then
  echo "ERROR: set FQDN (e.g. export FQDN=46hvbat.tak-hv-sandbox.se)"
  exit 2
fi

fail=0
say() { printf "\n== %s ==\n" "$*"; }
ok()  { printf "OK: %s\n" "$*"; }
bad() { printf "FAIL: %s\n" "$*"; fail=1; }

run() {
  local desc="$1"; shift
  if "$@"; then ok "$desc"; else bad "$desc"; fi
}

http_code() {
  # prints HTTP status code, or 000 on connect/TLS failure
  curl -sS -o /dev/null -w "%{http_code}" --max-time 6 "$1" || echo "000"
}

acceptable() {
  # acceptable <code> <list...>
  local code="$1"; shift
  for x in "$@"; do [[ "$code" == "$x" ]] && return 0; done
  return 1
}

say "systemd"
run "nginx active"      systemctl is-active --quiet nginx
run "takctl-web active" systemctl is-active --quiet takctl-web.service

say "nginx config"
run "nginx -t" sudo -n nginx -t >/dev/null 2>&1

say "local backend"
run "takctl health (127.0.0.1:8080)" curl -fsS --max-time 3 http://127.0.0.1:8080/api/health >/dev/null

echo "\n== public vhosts =="
# NOTE: Do not rely on DNS here. Force SNI+Host to $FQDN while connecting to localhost.
if [[ -z "${FQDN:-}" ]]; then
  say "WARN: FQDN not set; skipping public vhost checks"
else
  run "takctl via 443 (/takctl/api/health)" bash -lc 'code="$(curl -kfsS --max-time 6 -o /dev/null -w "%{http_code}" --resolve "${FQDN}:443:127.0.0.1" "https://${FQDN}/takctl/api/health" || true)"; [[ "$code" = "200" ]] || { echo "http=$code"; exit 1; }'
  run "frontdoor via 8446 (/Marti/api/version)" bash -lc 'code="$(curl -kfsS --max-time 6 -o /dev/null -w "%{http_code}" --resolve "${FQDN}:8446:127.0.0.1" "https://${FQDN}:8446/Marti/api/version" || true)"; [[ "$code" = "200" ]] || { echo "http=$code"; exit 1; }'
fi
say "ports (best-effort)"
run "tcp 80 listening"   sudo -n ss -ltnp | grep -qE ':80\s'
run "tcp 443 listening"  sudo -n ss -ltnp | grep -qE ':443\s'
run "tcp 8446 listening" sudo -n ss -ltnp | grep -qE ':8446\s'
run "tcp 8080 listening" sudo -n ss -ltnp | grep -qE ':8080\s'

# takctl webUI smoke (through nginx 443 vhost)
# Requires FQDN set (same as installer actions)
if [[ -n "${FQDN:-}" ]]; then
  run "takctl ui html"        curl -kfsS "https://127.0.0.1/takctl/" -H "Host: ${FQDN}" | head -n 2 | grep -qi '<!doctype html'
  run "takctl api health"     curl -kfsS "https://127.0.0.1/takctl/api/health" -H "Host: ${FQDN}" | grep -q '"status":"ok"'
else
  say "WARN: FQDN not set; skipping takctl nginx mount smoke checks"
fi


say "result"
if [[ "$fail" -eq 0 ]]; then
  echo "ALL GREEN"
  exit 0
else
  echo "SOME CHECKS FAILED"
  exit 1
fi
