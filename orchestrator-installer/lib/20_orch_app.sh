#!/usr/bin/env bash
set -euo pipefail

orch_app_install(){
  # place code
  install -d -m 0755 -o www-data -g www-data /opt/tak-orch
  rsync -a --delete ${BASE_DIR}/../orchestrator/ /opt/tak-orch/orchestrator/

  # venv
  if [[ ! -d /opt/tak-orch/.venv ]]; then
    python3 -m venv /opt/tak-orch/.venv
  fi
  /opt/tak-orch/.venv/bin/pip install --upgrade pip >/dev/null

  # deps: prefer requirements.txt if repo provides it, else fall back
  if [[ -f /opt/tak-orch/orchestrator/requirements.txt ]]; then
    /opt/tak-orch/.venv/bin/pip install -r /opt/tak-orch/orchestrator/requirements.txt >/dev/null
  else
    /opt/tak-orch/.venv/bin/pip install "boto3" "fastapi" "uvicorn[standard]" "jinja2" "pyyaml" "python-multipart" >/dev/null
  fi

  # systemd unit (source-controlled)
  install -m 0644 ${BASE_DIR}/../orchestrator/systemd/tak-orch.service /etc/systemd/system/taks-orch.service

  # ------------------------------------------------------------
  # Installer-owned defaults (runtime state)
  # - Source of truth: /opt/tak-orch/state/defaults.env
  # - We DO NOT overwrite existing defaults.env automatically
  #   (web UI will edit it later).
  # ------------------------------------------------------------
  install -d -m 0755 -o ubuntu -g ubuntu /opt/tak-orch/state
  install -d -m 0755 /etc/systemd/system/taks-orch.service.d

  # ------------------------------------------------------------
  # Operator env (KISS, deterministic)
  # - Drop-in always present (so /etc/taks/orchestrator.env is honored)
  # - Env file always readable by service user (ubuntu)
  # ------------------------------------------------------------
  install -d -m 0755 /etc/taks

  cat > /etc/systemd/system/taks-orch.service.d/10-local-env.conf <<'EOF'
[Service]
# Operator overrides (wins over /opt/tak-orch/state/defaults.env)
EnvironmentFile=-/etc/taks/orchestrator.env
EOF

  if [[ ! -f /etc/taks/orchestrator.env ]]; then
    cat > /etc/taks/orchestrator.env <<'EOF'
# Operator overrides for taks-orch (read by systemd)
# Keep this file SIMPLE and stable.
TAKS_LAUNCH_ENABLED=1
AWS_REGION=eu-north-1
AWS_DEFAULT_REGION=eu-north-1
# Optional (used by launcher):
#TAKS_AWS_SG_ID=sg-xxxxxxxx
#TAKS_AWS_KEY_NAME=your-key-name
EOF
  fi

  chown root:ubuntu /etc/taks/orchestrator.env
  chmod 0640 /etc/taks/orchestrator.env

  # kill legacy installer-managed drop-ins to avoid config split-brain
  rm -f /etc/systemd/system/taks-orch.service.d/10-aws.env.conf \
        /etc/systemd/system/taks-orch.service.d/20-launch-overrides.conf \
        /etc/systemd/system/taks-orch.service.d/21-network-overrides.conf \
        /etc/systemd/system/taks-orch.service.d/30-image-overrides.conf 2>/dev/null || true

  # pick a sane subnet default from IMDS (works without EC2 API perms)
  _imds_subnet_id=""
  if command -v curl >/dev/null 2>&1; then
    _token="$(curl -fsS -X PUT http://169.254.169.254/latest/api/token \
      -H "X-aws-ec2-metadata-token-ttl-seconds: 60" 2>/dev/null || true)"
    if [[ -n "${_token}" ]]; then
      _mac="$(curl -fsS -H "X-aws-ec2-metadata-token: ${_token}" \
        http://169.254.169.254/latest/meta-data/network/interfaces/macs/ 2>/dev/null \
        | head -n1 | tr -d '/' || true)"
      if [[ -n "${_mac}" ]]; then
        _imds_subnet_id="$(curl -fsS -H "X-aws-ec2-metadata-token: ${_token}" \
          "http://169.254.169.254/latest/meta-data/network/interfaces/macs/${_mac}/subnet-id" 2>/dev/null || true)"
      fi
    fi
  fi

  # Allow installer env to seed defaults (optional)
  : "${TAKS_CLOUD:=aws}"
  : "${TAKS_IMAGE_ID:=}"                 # empty => app may attempt auto-resolve
  : "${TAKS_SUBNET_ID:=${_imds_subnet_id}}"
  : "${TAKS_AWS_KEY_NAME:=}"             # empty by default (must be set for real launch)
  : "${TAKS_AWS_SG_ID:=}"                # empty by default (must be set for real launch)
  : "${TAKS_LAUNCH_ENABLED:=0}"

  if [[ ! -f /opt/tak-orch/state/defaults.env ]]; then
    cat > /opt/tak-orch/state/defaults.env <<EOF
# Managed by taks orchestrator-installer (seeded once on first install).
# WebUI will later edit this file.
TAKS_CLOUD=${TAKS_CLOUD}
TAKS_IMAGE_ID=${TAKS_IMAGE_ID}
TAKS_SUBNET_ID=${TAKS_SUBNET_ID}
TAKS_AWS_KEY_NAME=${TAKS_AWS_KEY_NAME}
TAKS_AWS_SG_ID=${TAKS_AWS_SG_ID}
TAKS_LAUNCH_ENABLED=${TAKS_LAUNCH_ENABLED}
EOF
    chown ubuntu:ubuntu /opt/tak-orch/state/defaults.env
    chmod 0644 /opt/tak-orch/state/defaults.env
  fi

  systemctl daemon-reload
  systemctl enable --now taks-orch.service
  systemctl restart taks-orch.service

  # ------------------------------------------------------------
  # Shared takctl splash bundle (installer-owned runtime assets)
  # Source: /opt/taks/takctl/web/{splash.css,splash.js,splash.fragment.html,assets/,css/}
  # Dest:   /opt/tak-orch/orchestrator/orchestrator_api/static/shared/takctl
  # ------------------------------------------------------------
  install -d -m 0755 -o ubuntu -g ubuntu /opt/tak-orch/orchestrator/orchestrator_api/static/shared/takctl
  rsync -a --delete ${BASE_DIR}/../takctl/web/ /opt/tak-orch/orchestrator/orchestrator_api/static/shared/takctl/

  # -------------------------------------------------------------------
  # ensure orchestrator shared login.role=true (Role field visible)
  # Node uses the same source bundle but should hide Role by default.
  # So we flip the DEST copy after rsync.
  # -------------------------------------------------------------------
  ## ensure orchestrator shared login.role=true
  python3 - <<'PY'
import json
from pathlib import Path
bp = Path('/opt/tak-orch/orchestrator/orchestrator_api/static/shared/takctl/assets/brand.json')
if bp.exists():
    o = json.loads(bp.read_text(encoding='utf-8'))
    if not isinstance(o, dict):
        o = {}
    login = o.get('login')
    if not isinstance(login, dict):
        login = {}
    o['login'] = login
    o['login']['role'] = True
    bp.write_text(json.dumps(o, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('patched:', bp, 'login.role=true')
else:
    print('missing:', bp)
PY


  # Wait for backend to be reachable (avoid nginx 502 race)
  echo "[orch-install] waiting for taks-orch backend on 127.0.0.1:8090 ..."
  for i in $(seq 1 20); do
    if curl -fsS http://127.0.0.1:8090/api/v1/status >/dev/null 2>&1; then
      echo "[orch-install] backend is up"
      break
    fi
    sleep 0.5
  done

}

orch_app_verify(){
  systemctl is-active --quiet taks-orch.service || die "taks-orch.service not active"
  curl -fsS https://${FQDN}/healthz >/dev/null || die "orch app healthz failed"
}
