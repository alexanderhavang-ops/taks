#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${ENV_FILE:-/etc/tak/install.env}"

log(){ echo "[$(date -Is)] $*"; }
die(){ echo "ERROR: $*" >&2; exit 1; }
require_root(){ [[ ${EUID:-999} -eq 0 ]] || die "must run as root"; }

load_env(){
  if [[ -f "$ENV_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$ENV_FILE"
  fi

  INSTALL_MODE="${INSTALL_MODE:-online}"  # online|offline

  BUNDLE_TGZ="${BUNDLE_TGZ:-}"
  BUNDLE_DIR="${BUNDLE_DIR:-/opt/taks/offline-bundle}"

  TAK_DEB="${TAK_DEB:-/opt/tak/install/takserver_5.6-RELEASE6_all.deb}"

  PUBLIC_PORT_ENROLL="${PUBLIC_PORT_ENROLL:-8446}"
}

require_identity(){
  : "${BATTALION:?missing BATTALION in /etc/tak/install.env}"
  : "${BASE_DOMAIN:?missing BASE_DOMAIN in /etc/tak/install.env}"
  : "${FQDN:?missing FQDN in /etc/tak/install.env}"
  : "${LE_EMAIL:?missing LE_EMAIL in /etc/tak/install.env}"
}
