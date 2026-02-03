#!/usr/bin/env bash
set -euo pipefail

# Smoketest needs root to read nginx/certs and query systemd cleanly.
if [[ "${EUID:-$(id -u)}" -ne 0 && "${TAKS_ELEVATED:-0}" != "1" ]]; then
  echo "INFO: smoketest requires root; re-exec with sudo"
  exec sudo -E TAKS_ELEVATED=1 "$0" "$@"
fi

say() { echo "== $* =="; }

run() {
  local label="$1"; shift
  echo "-- $label"
  "$@"
  echo
}

curl_code() {
  # Usage: curl_code <url> [extra curl args...]
  local url="$1"; shift
  local errf rc code err
  errf="$(mktemp)"
  set +e
  code="$(curl -kfsS --max-time 6 -o /dev/null -w '%{http_code}' "$url" "$@" 2>"$errf")"
  rc=$?
  set -e
  err="$(head -n 1 "$errf" || true)"
  rm -f "$errf"
  [[ -n "$code" ]] || code="000"
  echo "$rc $code $err"
}

say "systemd"
run "nginx active"      systemctl is-active --quiet nginx
run "takctl-web active" systemctl is-active --quiet takctl-web

say "nginx config"
run "nginx -t" nginx -t

say "local backend"
run "takctl health (localhost)" curl -fsS http://127.0.0.1:8080/api/health >/dev/null

say "public vhosts"
if [[ -z "${FQDN:-}" ]]; then
  echo "WARN: FQDN not set; skipping public vhost checks"
else
  run "takctl via 443 (/takctl/api/health)" bash -lc '
    set -euo pipefail
    read -r rc code err < <(curl_code \
      "https://${FQDN}/takctl/api/health" \
      --resolve "${FQDN}:443:127.0.0.1")
    if [[ "$code" != "200" ]]; then
      echo "rc=$rc http=$code err=$err"
      exit 1
    fi
  ' 2>/dev/null || {
    # re-run with helpers available in this shell (bash -lc loses functions)
    read -r rc code err < <(curl_code \
      "https://${FQDN}/takctl/api/health" \
      --resolve "${FQDN}:443:127.0.0.1")
    [[ "$code" == "200" ]] || { echo "rc=$rc http=$code err=$err"; exit 1; }
  }

  run "frontdoor via 8446 (/Marti/api/version)" bash -lc '
    set -euo pipefail
    read -r rc code err < <(curl_code \
      "https://${FQDN}:8446/Marti/api/version" \
      --resolve "${FQDN}:8446:127.0.0.1")
    case "$code" in
      200|401|403) exit 0 ;;
      *) echo "rc=$rc http=$code err=$err"; exit 1 ;;
    esac
  ' 2>/dev/null || {
    read -r rc code err < <(curl_code \
      "https://${FQDN}:8446/Marti/api/version" \
      --resolve "${FQDN}:8446:127.0.0.1")
    case "$code" in
      200|401|403) : ;;
      *) echo "rc=$rc http=$code err=$err"; exit 1 ;;
    esac
  }
fi

say "ports (best-effort)"
ss -ltnp | egrep ':(80|443|8446|8080)\s' || true

echo
echo "OK"
