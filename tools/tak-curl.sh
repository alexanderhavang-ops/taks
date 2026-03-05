#!/usr/bin/env bash
set -euo pipefail
arg="${1:-}"
if [[ -z "${arg}" ]]; then
  echo "Usage: $0 <path-or-url>" >&2
  exit 2
fi
scheme="${TAKS_SCHEME:-https}"
host="${TAKS_HOST:-46hvbat.tak-hv-sandbox.se}"
port="${TAKS_PORT:-}"
base="${scheme}://${host}"
if [[ -n "${port}" ]]; then base="${base}:${port}"; fi
if [[ "${arg}" =~ ^https?:// ]]; then
  url="${arg}"
else
  path="${arg}"
  [[ "${path}" != /* ]] && path="/${path}"
  if [[ "${path}" == /onboarding/* ]]; then path="/api${path}"; fi
  url="${base}${path}"
fi
echo "→ ${url}" >&2
curl_args=(-fsS)
if [[ "${TAKS_INSECURE:-0}" == "1" ]]; then curl_args+=(-k); fi
if [[ "${TAKS_VERBOSE:-0}" == "1" ]]; then curl_args+=(-v); fi
if [[ -n "${TAKS_USER:-}" && -n "${TAKS_PASSWORD:-}" ]]; then
  curl_args+=(-u "${TAKS_USER}:${TAKS_PASSWORD}")
fi
curl_args+=(-H "cache-control: no-store" -H "pragma: no-cache")
exec curl "${curl_args[@]}" "${url}"
