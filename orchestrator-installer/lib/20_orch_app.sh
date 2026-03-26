#!/usr/bin/env bash
set -euo pipefail

orch_app_install(){
  install -d -m 0755 -o www-data -g www-data /opt/tak-orch
  rsync -a --delete ${BASE_DIR}/../orchestrator/ /opt/tak-orch/orchestrator/

  if [[ ! -d /opt/tak-orch/.venv ]]; then
    python3 -m venv /opt/tak-orch/.venv
  fi
  /opt/tak-orch/.venv/bin/pip install --upgrade pip >/dev/null

  if [[ -f /opt/tak-orch/orchestrator/requirements.txt ]]; then
    /opt/tak-orch/.venv/bin/pip install -r /opt/tak-orch/orchestrator/requirements.txt >/dev/null
  else
    /opt/tak-orch/.venv/bin/pip install "boto3" "fastapi" "uvicorn[standard]" "jinja2" "pyyaml" "python-multipart" >/dev/null
  fi

  install -m 0644 ${BASE_DIR}/../orchestrator/systemd/tak-orch.service /etc/systemd/system/taks-orch.service

  install -d -m 0755 -o ubuntu -g ubuntu /opt/tak-orch/state
  install -d -m 0755 /etc/taks

  # Canonical config must exist. No env/default fallbacks.
  [[ -f /etc/taks/tak_orch.conf ]] || die "missing canonical config: /etc/taks/tak_orch.conf"
  [[ -f /etc/taks/secrets.conf ]] || die "missing canonical secrets: /etc/taks/secrets.conf"

  # Remove old env-based override files / drop-ins
  rm -f /etc/systemd/system/taks-orch.service.d/10-local-env.conf \
        /etc/systemd/system/taks-orch.service.d/10-aws.env.conf \
        /etc/systemd/system/taks-orch.service.d/20-launch-overrides.conf \
        /etc/systemd/system/taks-orch.service.d/21-network-overrides.conf \
        /etc/systemd/system/taks-orch.service.d/30-image-overrides.conf 2>/dev/null || true
  rmdir /etc/systemd/system/taks-orch.service.d 2>/dev/null || true
  rm -f /etc/taks/orchestrator.env /opt/tak-orch/state/defaults.env 2>/dev/null || true

  install -d -m 2775 -o ubuntu -g taks-state /opt/tak-orch/state/artifacts
  install -d -m 2775 -o ubuntu -g taks-state /opt/tak-orch/state/artifacts/takserver
  install -d -m 2775 -o ubuntu -g taks-state /opt/tak-orch/state/artifacts/taks
  install -d -m 2775 -o ubuntu -g taks-state /opt/tak-orch/state/artifacts/coturn
  install -d -m 2775 -o ubuntu -g taks-state /opt/tak-orch/state/artifacts/plugins
  install -d -m 2775 -o ubuntu -g taks-state /opt/tak-orch/state/bundles
  install -d -m 2775 -o ubuntu -g taks-state /opt/tak-orch/state/bundles/rendered

  systemctl daemon-reload
  systemctl enable --now taks-orch.service
  systemctl restart taks-orch.service

  install -d -m 0755 -o ubuntu -g ubuntu /opt/tak-orch/orchestrator/orchestrator_api/static/shared/takctl
  rsync -a --delete ${BASE_DIR}/../takctl/web/ /opt/tak-orch/orchestrator/orchestrator_api/static/shared/takctl/

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
