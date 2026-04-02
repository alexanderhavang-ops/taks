#!/usr/bin/env bash
set -euo pipefail

orch_materialize_runtime_config(){
  local src_root="${BASE_DIR}/../orchestrator"
  local runtime_root="/opt/tak-orch/orchestrator"
  local preserve_root="${1:-}"
  local state_root="/opt/tak-orch/state"

  python3 - "$src_root" "$runtime_root" "$preserve_root" "$state_root" <<'PY'
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

src_root = Path(sys.argv[1])
runtime_root = Path(sys.argv[2])
preserve_root = Path(sys.argv[3]) if sys.argv[3] else None
state_root = Path(sys.argv[4])

src_conf_d = src_root / "conf.d"
src_secrets_d = src_root / "secrets.d"
src_confmeta = src_root / "confmeta"

dst_conf_d = runtime_root / "conf.d"
dst_secrets_d = runtime_root / "secrets.d"
dst_confmeta = runtime_root / "confmeta"

bootstrap_root = Path("/etc/taks-bootstrap.d")
bootstrap_conf_d = bootstrap_root / "config.d"
bootstrap_secrets_d = bootstrap_root / "secrets.d"

marker = state_root / ".orchestrator-bootstrap-imported-v1"

def parse_kv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip()
        if k:
            out[k] = v
    return out

def write_kv(path: Path, values: dict[str, str], mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [f"{k} = {values.get(k, '')}" for k in sorted(values.keys())]
    rows.append("")
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text("\n".join(rows), encoding="utf-8")
    os.chmod(tmp, mode)
    tmp.replace(path)

def component_files(d: Path) -> dict[str, Path]:
    out: dict[str, Path] = {}
    if not d.exists() or not d.is_dir():
        return out
    for p in sorted(d.iterdir()):
        if not p.is_file():
            continue
        n = p.name
        if n.endswith(".conf.template"):
            out[n[:-len(".template")]] = p
        elif n.endswith(".conf"):
            out[n] = p
    return out

def bootstrap_files(d: Path) -> dict[str, Path]:
    out: dict[str, Path] = {}
    if not d.exists() or not d.is_dir():
        return out
    for p in sorted(d.iterdir()):
        if p.is_file() and p.name.endswith(".conf"):
            out[p.name] = p
    return out

def existing_files(d: Path) -> dict[str, Path]:
    out: dict[str, Path] = {}
    if not d.exists() or not d.is_dir():
        return out
    for p in sorted(d.iterdir()):
        if p.is_file() and p.name.endswith(".conf"):
            out[p.name] = p
    return out

def load_meta(src_dir: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    if not src_dir.exists() or not src_dir.is_dir():
        return out
    for p in sorted(src_dir.iterdir()):
        if not p.is_file():
            continue
        if not (p.name.endswith(".json") or p.name.endswith(".json.template")):
            continue
        obj = json.loads(p.read_text(encoding="utf-8"))
        component = str(obj.get("component") or p.stem.replace(".json", "")).strip()
        fields = obj.get("fields") or {}
        if not isinstance(fields, dict):
            continue
        out[component] = fields
    return out

def render_component_dir(src_dir: Path, preserved_dir: Path | None, bootstrap_dir: Path, dst_dir: Path, mode: int, use_bootstrap: bool) -> None:
    src_map = component_files(src_dir)
    preserved_map = existing_files(preserved_dir) if preserved_dir else {}
    bootstrap_map = bootstrap_files(bootstrap_dir) if use_bootstrap else {}
    names = sorted(set(src_map) | set(preserved_map) | set(bootstrap_map))

    dst_dir.mkdir(parents=True, exist_ok=True)

    for p in sorted(dst_dir.glob("*.conf")):
        if p.name not in names:
            p.unlink()

    for name in names:
        merged: dict[str, str] = {}
        if name in src_map:
            merged.update(parse_kv(src_map[name]))
        if name in preserved_map:
            merged.update(parse_kv(preserved_map[name]))
        if name in bootstrap_map:
            merged.update(parse_kv(bootstrap_map[name]))
        write_kv(dst_dir / name, merged, mode)

meta = load_meta(src_confmeta)

# wipe runtime confmeta and re-install from source
dst_confmeta.mkdir(parents=True, exist_ok=True)
for old in sorted(dst_confmeta.iterdir()):
    if old.is_file() or old.is_symlink():
        old.unlink()
    elif old.is_dir():
        shutil.rmtree(old)

if src_confmeta.exists() and src_confmeta.is_dir():
    for p in sorted(src_confmeta.iterdir()):
        if not p.is_file():
            continue
        if not (p.name.endswith(".json") or p.name.endswith(".json.template")):
            continue
        dst_name = p.name[:-len(".template")] if p.name.endswith(".template") else p.name
        dst = dst_confmeta / dst_name
        dst.write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
        os.chmod(dst, 0o644)

use_bootstrap = not marker.exists()

preserved_conf_d = (preserve_root / "conf.d") if preserve_root else None
preserved_secrets_d = (preserve_root / "secrets.d") if preserve_root else None

render_component_dir(
    src_dir=src_conf_d,
    preserved_dir=preserved_conf_d,
    bootstrap_dir=bootstrap_conf_d,
    dst_dir=dst_conf_d,
    mode=0o640,
    use_bootstrap=use_bootstrap,
)

render_component_dir(
    src_dir=src_secrets_d,
    preserved_dir=preserved_secrets_d,
    bootstrap_dir=bootstrap_secrets_d,
    dst_dir=dst_secrets_d,
    mode=0o640,
    use_bootstrap=use_bootstrap,
)

state_root.mkdir(parents=True, exist_ok=True)
if use_bootstrap:
    marker.write_text("imported\n", encoding="utf-8")

print(f"materialized conf.d -> {dst_conf_d}")
print(f"materialized secrets.d -> {dst_secrets_d}")
print(f"installed confmeta -> {dst_confmeta}")
print(f"bootstrap import used: {str(use_bootstrap).lower()}")
PY

  chown -R ubuntu:ubuntu /opt/tak-orch/orchestrator/conf.d /opt/tak-orch/orchestrator/secrets.d /opt/tak-orch/orchestrator/confmeta
  find /opt/tak-orch/orchestrator/conf.d -type f -name '*.conf' -exec chmod 0640 {} \;
  find /opt/tak-orch/orchestrator/secrets.d -type f -name '*.conf' -exec chmod 0640 {} \;
  find /opt/tak-orch/orchestrator/confmeta -type f -name '*.json' -exec chmod 0644 {} \;
}

orch_app_install(){
  local preserve=""
  if [[ -d /opt/tak-orch/orchestrator ]]; then
    preserve="$(mktemp -d /tmp/tak-orch-preserve.XXXXXX)"
    install -d -m 0755 "$preserve"
    if [[ -d /opt/tak-orch/orchestrator/conf.d ]]; then
      rsync -a /opt/tak-orch/orchestrator/conf.d/ "$preserve/conf.d/"
    fi
    if [[ -d /opt/tak-orch/orchestrator/secrets.d ]]; then
      rsync -a /opt/tak-orch/orchestrator/secrets.d/ "$preserve/secrets.d/"
    fi
  fi

  install -d -m 0755 -o www-data -g www-data /opt/tak-orch
  rsync -a --delete ${BASE_DIR}/../orchestrator/ /opt/tak-orch/orchestrator/

  orch_materialize_runtime_config "$preserve"

  if [[ -n "$preserve" && -d "$preserve" ]]; then
    rm -rf "$preserve"
  fi

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
  install -d -m 2775 -o ubuntu -g taks-state /opt/tak-orch/state/artifacts
  install -d -m 2775 -o ubuntu -g taks-state /opt/tak-orch/state/artifacts/takserver
  install -d -m 2775 -o ubuntu -g taks-state /opt/tak-orch/state/artifacts/taks
  install -d -m 2775 -o ubuntu -g taks-state /opt/tak-orch/state/artifacts/coturn
  install -d -m 2775 -o ubuntu -g taks-state /opt/tak-orch/state/artifacts/plugins
  install -d -m 2775 -o ubuntu -g taks-state /opt/tak-orch/state/bundles
  install -d -m 2775 -o ubuntu -g taks-state /opt/tak-orch/state/bundles/rendered

  # old canonical /etc/taks/*.conf is no longer authoritative here
  rm -f /etc/taks/tak_orch.conf /etc/taks/secrets.conf 2>/dev/null || true

  rm -f /etc/systemd/system/taks-orch.service.d/10-local-env.conf \
        /etc/systemd/system/taks-orch.service.d/10-aws.env.conf \
        /etc/systemd/system/taks-orch.service.d/20-launch-overrides.conf \
        /etc/systemd/system/taks-orch.service.d/21-network-overrides.conf \
        /etc/systemd/system/taks-orch.service.d/30-image-overrides.conf 2>/dev/null || true
  rmdir /etc/systemd/system/taks-orch.service.d 2>/dev/null || true
  rm -f /etc/taks/orchestrator.env /opt/tak-orch/state/defaults.env 2>/dev/null || true

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
