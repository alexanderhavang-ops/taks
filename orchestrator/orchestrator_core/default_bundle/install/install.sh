#!/usr/bin/env bash
set -euo pipefail

echo "== TAKS default bundle: install starting =="

# Basic node config location (future: hostname, slogan, branding, etc)
install -d -m 0755 /etc/taks

# If a node.env was included (from unit overlay), install it
if [[ -f ./install/node.env ]]; then
  install -m 0644 ./install/node.env /etc/taks/node.env
  echo "installed /etc/taks/node.env"
fi

# Placeholder: branding assets
# (unit overlay can drop ./assets/logo.png etc; we just place it predictably)
if [[ -f ./assets/logo.png ]]; then
  install -d -m 0755 /opt/taks/assets
  install -m 0644 ./assets/logo.png /opt/taks/assets/logo.png
  echo "installed /opt/taks/assets/logo.png"
fi

echo "== TAKS default bundle: install complete =="

