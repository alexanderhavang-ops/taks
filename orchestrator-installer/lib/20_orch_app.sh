#!/usr/bin/env bash
set -euo pipefail

orch_app_install(){
  # place code
  install -d -m 0755 -o www-data -g www-data /opt/tak-orch
  rsync -a --delete /home/ubuntu/taks/orchestrator/ /opt/tak-orch/orchestrator/

  # venv
  if [[ ! -d /opt/tak-orch/.venv ]]; then
    python3 -m venv /opt/tak-orch/.venv
  fi

  /opt/tak-orch/.venv/bin/pip install --upgrade pip >/dev/null
  /opt/tak-orch/.venv/bin/pip install "boto3" "fastapi" "uvicorn[standard]" >/dev/null

  # systemd
  install -m 0644 /home/ubuntu/taks/orchestrator/systemd/tak-orch.service /etc/systemd/system/tak-orch.service
  systemctl daemon-reload
  systemctl enable --now tak-orch.service
}

orch_app_verify(){
  systemctl is-active --quiet tak-orch.service || die "tak-orch.service not active"
  curl -fsS https://${FQDN}/healthz >/dev/null || die "orch app healthz failed"
}
