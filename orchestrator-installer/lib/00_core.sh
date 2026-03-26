#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${ENV_FILE:-/etc/tak-orch/install.env}"
ORCH_CONF_FILE="${ORCH_CONF_FILE:-/etc/taks/tak_orch.conf}"

log(){ echo "[$(date -Is)] $*"; }
die(){ echo "ERROR: $*" >&2; exit 1; }
require_root(){ [[ ${EUID:-999} -eq 0 ]] || die "must run as root"; }

_conf_py(){
  local expr="${1:?missing python expr}"
  python3 - "$ORCH_CONF_FILE" "$expr" <<'PY'
from pathlib import Path
import sys
try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

conf_path = Path(sys.argv[1])
expr = sys.argv[2]

if not conf_path.exists():
    raise SystemExit(f"missing config file: {conf_path}")

raw = tomllib.loads(conf_path.read_text(encoding="utf-8"))

def req(section, key):
    sec = raw.get(section)
    if not isinstance(sec, dict):
        raise SystemExit(f"missing section: {section}")
    val = sec.get(key)
    if not isinstance(val, str) or not val.strip():
        raise SystemExit(f"missing required string: {section}.{key}")
    return val.strip()

mapping = {
    "identity.orchestrator_fqdn": ("identity", "orchestrator_fqdn"),
    "letsencrypt.email": ("letsencrypt", "email"),
    "letsencrypt.mode": ("letsencrypt", "mode"),
    "letsencrypt.wildcard_zone": ("letsencrypt", "wildcard_zone"),
    "letsencrypt.artifact_cert_dir": ("letsencrypt", "artifact_cert_dir"),
}

if expr not in mapping:
    raise SystemExit(f"unsupported expr: {expr}")

section, key = mapping[expr]
print(req(section, key))
PY
}

load_env(){
  [[ -f "$ENV_FILE" ]] || die "missing env file: $ENV_FILE"
  # shellcheck disable=SC1090
  source "$ENV_FILE"

  FQDN="$(_conf_py 'identity.orchestrator_fqdn')"
  LE_EMAIL="$(_conf_py 'letsencrypt.email')"

  export FQDN
  export LE_EMAIL

  : "${FQDN:?}" "${LE_EMAIL:?}"
}
