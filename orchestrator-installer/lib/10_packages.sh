#!/usr/bin/env bash
set -euo pipefail

pkg_install(){
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -y
  apt-get install -y \
    git jq dnsutils \
    nginx certbot python3-certbot-nginx \
    python3-venv python3-pip \
    ca-certificates curl unzip ssl-cert
  systemctl enable --now nginx
}
