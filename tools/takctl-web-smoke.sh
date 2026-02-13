#!/usr/bin/env bash
set -euo pipefail

BASE="${BASE:-https://127.0.0.1}"
MOUNT="${MOUNT:-/takctl}"
URL_BASE="${BASE%/}${MOUNT}"
CURL="curl -sS -k --connect-timeout 3 --max-time 15"

fail() { echo "FAIL: $*" >&2; exit 1; }
ok()   { echo "OK:   $*"; }

need_cmd() { command -v "$1" >/dev/null 2>&1 || fail "missing required command: $1"; }
need_cmd curl
need_cmd python3
need_cmd grep
need_cmd sed
need_cmd awk

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

fetch_body() {
  $CURL "$1" -o "$2" || fail "GET failed: $1"
}

fetch_head() {
  $CURL -D- "$1" -o /dev/null >"$2" || fail "HEAD failed: $1"
}

status_of() { awk 'toupper($0) ~ /^HTTP\// {print $2; exit}' "$1"; }
ctype_of()  { awk -F': ' 'tolower($1)=="content-type"{print tolower($2); exit}' "$1" | tr -d '\r'; }

require_status() {
  fetch_head "$1" "$tmp/h"
  st="$(status_of "$tmp/h")"
  [ "$st" = "$2" ] || fail "$1 status=$st (want $2)"
  ok "$1 status=$st"
}

require_ctype_contains() {
  fetch_head "$1" "$tmp/h"
  ct="$(ctype_of "$tmp/h")"
  echo "$ct" | grep -qi "$2" || fail "$1 content-type=$ct (want contains $2)"
  ok "$1 content-type ok ($2)"
}

require_body_has() {
  fetch_body "$1" "$tmp/b"
  grep -Fq "$2" "$tmp/b" || fail "$1 missing string: $2"
  ok "$1 has string: $2"
}

require_body_lacks() {
  fetch_body "$1" "$tmp/b"
  grep -Fq "$2" "$tmp/b" && fail "$1 unexpectedly contains: $2"
  ok "$1 lacks string: $2"
}

echo "== takctl web smoke =="
echo "BASE=$BASE"
echo "MOUNT=$MOUNT"
echo "URL_BASE=$URL_BASE"
echo

# Core endpoints
require_status "$URL_BASE/" 200
require_ctype_contains "$URL_BASE/" text/html

require_status "$URL_BASE/styles.css" 200
require_ctype_contains "$URL_BASE/styles.css" text/css

require_status "$URL_BASE/splash.css" 200
require_ctype_contains "$URL_BASE/splash.css" text/css

require_status "$URL_BASE/api/health" 200
require_ctype_contains "$URL_BASE/api/health" application/json

# Health JSON validation
fetch_body "$URL_BASE/api/health" "$tmp/health.json"
python3 - <<'PY' "$tmp/health.json"
import json, sys
j=json.load(open(sys.argv[1]))
required=["status","apply_ts_utc","coreconfig_path","auth_xml_path"]
missing=[k for k in required if k not in j]
if missing:
    raise SystemExit("missing keys: "+", ".join(missing))
print("health json ok")
PY
ok "$URL_BASE/api/health json keys ok"
echo

# index overlay model
require_body_has "$URL_BASE/" "__splash"
require_body_has "$URL_BASE/" "splash.js"
ok "index.html overlay model ok"
echo

# splash.html contract
require_status "$URL_BASE/splash.html" 200
require_ctype_contains "$URL_BASE/splash.html" text/html
require_body_has "$URL_BASE/splash.html" "<!doctype html>"
require_body_has "$URL_BASE/splash.html" 'href="./splash.css"'
require_body_has "$URL_BASE/splash.html" 'src="./splash.js"'
require_body_has "$URL_BASE/splash.html" 'id="__splash"'
require_body_lacks "$URL_BASE/splash.html" "tools/takctl-web-smoke.sh"

echo
ok "takctl web smoke PASSED"
