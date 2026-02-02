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

say "public vhosts"
c="$(http_code "https://${FQDN}/takctl/api/health")"
if acceptable "$c" 200; then ok "takctl via 443 (/takctl/api/health) http=$c"; else bad "takctl via 443 (/takctl/api/health) http=$c"; fi

# For 8446 "frontdoor", we only assert that nginx+proxy is alive.
# 200 is great; 301/302 are fine; 401/403 can be normal for Marti endpoints.
c="$(http_code "https://${FQDN}:8446/Marti/api/version")"
if acceptable "$c" 200 301 302 401 403; then
  ok "frontdoor via 8446 (/Marti/api/version) http=$c"
else
  bad "frontdoor via 8446 (/Marti/api/version) http=$c"
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
