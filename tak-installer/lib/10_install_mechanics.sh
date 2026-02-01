#!/usr/bin/env bash
set -euo pipefail

pkg_install_online(){
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -y
  apt-get install -y \
    ca-certificates curl jq openssl unzip \
    default-jre-headless \
    postgresql postgresql-client \
    nginx \
    xmlstarlet \
    certbot python3-certbot-nginx
}

require_offline_bundle(){
  if [[ -n "$BUNDLE_TGZ" ]]; then
    [[ -f "$BUNDLE_TGZ" ]] || die "BUNDLE_TGZ not found: $BUNDLE_TGZ"
    mkdir -p "$BUNDLE_DIR"
    log "Extracting bundle: $BUNDLE_TGZ -> $BUNDLE_DIR"
    tar -C "$BUNDLE_DIR" -xzf "$BUNDLE_TGZ"
  fi

  [[ -d "$BUNDLE_DIR/debs" ]] || die "missing bundle debs dir: $BUNDLE_DIR/debs"
  [[ -f "$BUNDLE_DIR/tak/takserver.deb" ]] || die "missing TAK deb: $BUNDLE_DIR/tak/takserver.deb"
}

offline_install_debs(){
  log "Offline installing OS deps from: $BUNDLE_DIR/debs"
  shopt -s nullglob
  local debs=( "$BUNDLE_DIR/debs"/*.deb )
  shopt -u nullglob
  [[ ${#debs[@]} -gt 0 ]] || die "no .deb files in $BUNDLE_DIR/debs"

  local pass
  for pass in 1 2 3 4 5; do
    log "dpkg pass $pass/5"
    set +e
    dpkg -i "$BUNDLE_DIR/debs"/*.deb >/tmp/tak-offline-dpkg.$pass.log 2>&1
    rc=$?
    dpkg --configure -a >>/tmp/tak-offline-dpkg.$pass.log 2>&1
    rc2=$?
    set -e

    if [[ $rc -eq 0 && $rc2 -eq 0 ]]; then
      log "dpkg converged successfully"
      return 0
    fi

    log "dpkg not yet clean (rc=$rc rc2=$rc2); continuing"
  done

  die "offline deb install did not converge after 5 passes. See /tmp/tak-offline-dpkg.*.log"
}

install_tak_deb(){
  local deb="$1"
  [[ -f "$deb" ]] || die "TAK deb not found: $deb"

  if dpkg -s takserver >/dev/null 2>&1; then
    log "TAK already installed (dpkg)."
    return 0
  fi

  log "Installing TAK deb: $deb"
  dpkg -i "$deb" || die "TAK deb install failed"
}