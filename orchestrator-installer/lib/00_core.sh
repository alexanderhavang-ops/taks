#!/usr/bin/env bash
set -euo pipefail

# Installer env (FQDN + LE_EMAIL live here)
ENV_FILE="${ENV_FILE:-/etc/tak-orch/install.env}"

log(){ echo "[$(date -Is)] $*"; }
die(){ echo "ERROR: $*" >&2; exit 1; }
require_root(){ [[ ${EUID:-999} -eq 0 ]] || die "must run as root"; }

load_env(){
  [[ -f "$ENV_FILE" ]] || die "missing env file: $ENV_FILE"
  # shellcheck disable=SC1090
  source "$ENV_FILE"

  # Also load runtime defaults if present (UI password/secret, cloud config, etc.)
  # This keeps headless flows consistent without moving FQDN/LE_EMAIL yet.
  if [[ -f /opt/tak-orch/state/defaults.env ]]; then
    # shellcheck disable=SC1091
    source /opt/tak-orch/state/defaults.env
  fi

  : "${FQDN:?}" "${LE_EMAIL:?}"
}
