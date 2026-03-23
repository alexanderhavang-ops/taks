#!/usr/bin/env bash
set -euo pipefail

RUNTIME_DIR="/opt/tak/tools/takctl"
PY="${RUNTIME_DIR}/.venv/bin/python"

if [[ ! -x "$PY" ]]; then
  echo "ERROR: missing python venv at: $PY" >&2
  exit 2
fi

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

echo "## LLM run"
echo "runtime dir: ${RUNTIME_DIR}"
echo "domain: ${domain}"
echo "phases: ${phases[*]}"
echo

run_as_tak() {
  if [[ "$(id -un)" == "tak" ]]; then
    "$@"
  else
    sudo -u tak -g tak "$@"
  fi
}

cd "$RUNTIME_DIR"

run_one() {
  local ph="$1"
  echo "## RUN ${ph}"
  run_as_tak "$PY" -m takctl.services.llm2.runner --phase "$ph" --domain "$domain" --once
  echo
}

for ph in "${phases[@]}"; do
  run_one "$ph"
done
