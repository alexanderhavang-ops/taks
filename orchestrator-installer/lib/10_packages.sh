#!/usr/bin/env bash
set -euo pipefail

pkg_install(){
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -y
  apt-get install -y \
    git awscli jq dnsutils \
    nginx certbot python3-certbot-nginx \
    ca-certificates curl unzip
  systemctl enable --now nginx
}
