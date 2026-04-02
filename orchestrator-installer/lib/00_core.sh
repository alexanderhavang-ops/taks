#!/usr/bin/env bash
set -euo pipefail

log(){
  printf '[%s] %s\n' "$(date --iso-8601=seconds)" "$*"
}

die(){
  log "$*"
  exit 1
}

require_root(){
  [[ "$(id -u)" -eq 0 ]] || die "must run as root"
}

_bootstrap_hint(){
  cat >&2 <<'TXT'

Bootstrap config missing or incomplete.

First-time install requires bootstrap files in:
  /etc/taks-bootstrap.d/config.d/core.conf
  /etc/taks-bootstrap.d/secrets.d/auth.conf

Use these source examples:
  /opt/taks/orchestrator/bootstrap/config.d/core.conf.example
  /opt/taks/orchestrator/bootstrap/secrets.d/auth.conf.example

Example:
  sudo install -d -m 0755 /etc/taks-bootstrap.d/config.d /etc/taks-bootstrap.d/secrets.d
  sudo cp /opt/taks/orchestrator/bootstrap/config.d/core.conf.example /etc/taks-bootstrap.d/config.d/core.conf
  sudo cp /opt/taks/orchestrator/bootstrap/secrets.d/auth.conf.example /etc/taks-bootstrap.d/secrets.d/auth.conf
  sudo editor /etc/taks-bootstrap.d/config.d/core.conf
  sudo editor /etc/taks-bootstrap.d/secrets.d/auth.conf

TXT
}

load_env(){
  local exports
  exports="$(
    PYTHONPATH="${BASE_DIR}/../orchestrator" python3 - <<'PY'
from orchestrator_core.config import load_orch_config

cfg = load_orch_config()

def q(v: str) -> str:
    s = "" if v is None else str(v)
    return "'" + s.replace("'", "'\"'\"'") + "'"

print(f"export FQDN={q(cfg.identity.orchestrator_fqdn)}")
print(f"export LE_EMAIL={q(cfg.letsencrypt.email)}")
print(f"export LE_MODE={q(cfg.letsencrypt.mode)}")
print(f"export LE_WILDCARD_ZONE={q(cfg.letsencrypt.wildcard_zone)}")
print(f"export ARTIFACT_CERT_DIR={q(cfg.letsencrypt.artifact_cert_dir)}")
print(f"export PUBLIC_BASE_URL={q(cfg.identity.public_base_url)}")
PY
  )"

  eval "$exports"

  if [[ -z "${FQDN:-}" ]]; then
    _bootstrap_hint
    die "missing orchestrator_fqdn in runtime config"
  fi

  if [[ -z "${PUBLIC_BASE_URL:-}" ]]; then
    _bootstrap_hint
    die "missing public_base_url in runtime config"
  fi

  if [[ -z "${LE_MODE:-}" ]]; then
    _bootstrap_hint
    die "missing letsencrypt_mode in runtime config"
  fi

  case "${LE_MODE}" in
    dns-route53|dns_route53|wildcard_dns_01|WILDCARD_DNS_01)
      if [[ -z "${LE_EMAIL:-}" ]]; then
        _bootstrap_hint
        die "missing letsencrypt_email in runtime config"
      fi
      if [[ -z "${LE_WILDCARD_ZONE:-}" ]]; then
        _bootstrap_hint
        die "missing letsencrypt_wildcard_zone in runtime config"
      fi
      ;;
  esac
}
