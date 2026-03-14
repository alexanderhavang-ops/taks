#!/usr/bin/env bash
set -euo pipefail

RUNTIME_DIR="/opt/tak/tools/takctl"
PY="${RUNTIME_DIR}/.venv/bin/python"

DB_ENV="${RUNTIME_DIR}/secrets/db.env"
LLM_ENV="${RUNTIME_DIR}/secrets/llm.env"

if [[ ! -x "$PY" ]]; then
  echo "ERROR: missing python venv at: $PY" >&2
  exit 2
fi

set -a
if [[ -f "$DB_ENV" ]]; then
  . "$DB_ENV"
fi
if [[ -f "$LLM_ENV" ]]; then
  . "$LLM_ENV"
fi
set +a

export TAKCTL_CONFIG="${TAKCTL_CONFIG:-${RUNTIME_DIR}/takctl.conf}"
export TAKCTL_STATE_DIR="${TAKCTL_STATE_DIR:-${RUNTIME_DIR}/state}"

domain="${1:-}"
ph_from="${2:-}"
ph_to="${3:-}"

if [[ -z "$domain" || -z "$ph_from" ]]; then
  echo "Usage: $0 <domain|all> <phase_from> [phase_to]" >&2
  exit 2
fi
if [[ -z "$ph_to" ]]; then
  ph_to="$ph_from"
fi

norm_phase() {
  local p="$1"
  case "$p" in
    phase1|phase2|phase3) echo "$p" ;;
    1) echo "phase1" ;;
    2) echo "phase2" ;;
    3) echo "phase3" ;;
    *) echo "" ;;
  esac
}

ph_from="$(norm_phase "$ph_from")"
ph_to="$(norm_phase "$ph_to")"
if [[ -z "$ph_from" || -z "$ph_to" ]]; then
  echo "ERROR: phases must be phase1|phase2|phase3 (or 1|2|3)" >&2
  exit 2
fi

phases=()
case "${ph_from}:${ph_to}" in
  phase1:phase1) phases=(phase1) ;;
  phase2:phase2) phases=(phase2) ;;
  phase3:phase3) phases=(phase3) ;;
  phase1:phase2) phases=(phase1 phase2) ;;
  phase2:phase3) phases=(phase2 phase3) ;;
  phase1:phase3) phases=(phase1 phase2 phase3) ;;
  *)
    echo "ERROR: invalid phase range ${ph_from} -> ${ph_to}" >&2
    exit 2
    ;;
esac

prov="${TAKCTL_LLM_PROVIDER:-local}"
lurl="${TAKCTL_LLM_URL:-http://127.0.0.1:8090/v1/completions}"
lmodel="${TAKCTL_LLM_MODEL:-local-small}"
areg="${TAKCTL_AWS_REGION:-${AWS_REGION:-}}"
bmodel="${TAKCTL_BEDROCK_MODEL_ID:-}"
p3mode="${TAKCTL_LLM2_PHASE3_MODE:-fallback}"
kset="false"
if [[ -n "${AWS_BEARER_TOKEN_BEDROCK:-}" ]]; then kset="true"; fi

echo "## LLM env overlay"
echo "provider: ${prov}"
echo "local url: ${lurl}"
echo "local model: ${lmodel}"
echo "bedrock region: ${areg}"
echo "bedrock model: ${bmodel}"
echo "phase3 mode: ${p3mode}"
echo "bedrock key set: ${kset}"
echo

if [[ "$domain" != "all" ]]; then
  echo "## NOTE: domain='$domain' requested, but runner currently has no domain selector; running ALL domains."
  echo
fi

run_as_tak() {
  if [[ "$(id -un)" == "tak" ]]; then
    env \
      TAKCTL_CONFIG="${TAKCTL_CONFIG:-}" \
      TAKCTL_STATE_DIR="${TAKCTL_STATE_DIR:-}" \
      TAKCTL_LLM_PROVIDER="${TAKCTL_LLM_PROVIDER:-}" \
      TAKCTL_LLM_URL="${TAKCTL_LLM_URL:-}" \
      TAKCTL_LLM_MODEL="${TAKCTL_LLM_MODEL:-}" \
      TAKCTL_AWS_REGION="${TAKCTL_AWS_REGION:-}" \
      AWS_REGION="${AWS_REGION:-}" \
      TAKCTL_BEDROCK_MODEL_ID="${TAKCTL_BEDROCK_MODEL_ID:-}" \
      AWS_BEARER_TOKEN_BEDROCK="${AWS_BEARER_TOKEN_BEDROCK:-}" \
      TAKCTL_LLM2_PHASE3_MODE="${TAKCTL_LLM2_PHASE3_MODE:-}" \
      "$@"
  else
    sudo -u tak -g tak env \
      TAKCTL_CONFIG="${TAKCTL_CONFIG:-}" \
      TAKCTL_STATE_DIR="${TAKCTL_STATE_DIR:-}" \
      TAKCTL_LLM_PROVIDER="${TAKCTL_LLM_PROVIDER:-}" \
      TAKCTL_LLM_URL="${TAKCTL_LLM_URL:-}" \
      TAKCTL_LLM_MODEL="${TAKCTL_LLM_MODEL:-}" \
      TAKCTL_AWS_REGION="${TAKCTL_AWS_REGION:-}" \
      AWS_REGION="${AWS_REGION:-}" \
      TAKCTL_BEDROCK_MODEL_ID="${TAKCTL_BEDROCK_MODEL_ID:-}" \
      AWS_BEARER_TOKEN_BEDROCK="${AWS_BEARER_TOKEN_BEDROCK:-}" \
      TAKCTL_LLM2_PHASE3_MODE="${TAKCTL_LLM2_PHASE3_MODE:-}" \
      "$@"
  fi
}

cd "$RUNTIME_DIR"

run_one() {
  local ph="$1"
  echo "## RUN ${ph}"
  run_as_tak "$PY" -m takctl.services.llm2.runner --phase "$ph" --once
  echo
}

for ph in "${phases[@]}"; do
  run_one "$ph"
done
