#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${ENV_FILE:-/etc/tak-orch/install.env}"

log(){ echo "[$(date -Is)] $*"; }
die(){ echo "ERROR: $*" >&2; exit 1; }
require_root(){ [[ ${EUID:-999} -eq 0 ]] || die "must run as root"; }

load_env(){
  [[ -f "$ENV_FILE" ]] || die "missing env file: $ENV_FILE"
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  : "${FQDN:?}" "${LE_EMAIL:?}"
}
