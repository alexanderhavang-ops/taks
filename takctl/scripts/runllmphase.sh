#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'TXT'
Usage:
  runllmphase.sh <all> <fromphase> <tophase>

Examples:
  runllmphase.sh all phase1 phase1
  runllmphase.sh all phase1 phase2
  runllmphase.sh all phase1 phase3

Notes:
- Always runs ALL domains (runner handles them)
- Uses runtime venv
- Re-execs as tak user automatically
- ALWAYS prints trace summaries after each phase (success or fail)
TXT
}

DOM="${1:-}"
FROM="${2:-}"
TO="${3:-}"

if [[ -z "$DOM" || -z "$FROM" || -z "$TO" ]]; then
  usage
  exit 2
fi

if [[ "$DOM" != "all" ]]; then
  echo "Only 'all' is supported (KISS mode)." >&2
  exit 2
fi

phase_num() {
  case "$1" in
    phase1) echo 1 ;;
    phase2) echo 2 ;;
    phase3) echo 3 ;;
    *) echo 0 ;;
  esac
}

F="$(phase_num "$FROM")"
T="$(phase_num "$TO")"

if [[ "$F" -eq 0 || "$T" -eq 0 || "$F" -gt "$T" ]]; then
  echo "Invalid phase range: $FROM -> $TO" >&2
  exit 2
fi

RUNTIME="/opt/tak/tools/takctl"
PY="$RUNTIME/.venv/bin/python"
STATE="$RUNTIME/state"

if [[ "$(id -un)" != "tak" ]]; then
  exec sudo -u tak -g tak \
    PYTHONPATH="$RUNTIME" \
    TAKCTL_STATE_DIR="$STATE" \
    "$RUNTIME/scripts/runllmphase.sh" "$DOM" "$FROM" "$TO"
fi

cd "$RUNTIME"
export PYTHONPATH="$RUNTIME"
export TAKCTL_STATE_DIR="$STATE"

print_traces() {
  local ph="$1"
  local root="$STATE/llm2/latest"
  echo "## TRACE SUMMARY ($ph)"
  find "$root" -maxdepth 3 -type f -path "*/$ph/trace.json" -print 2>/dev/null | sort | while read -r t; do
    jq -r '
      [
        (.domain // "unknown"),
        (.ok|tostring),
        ((.error//"")|tostring),
        ((.elapsed_ms//"")|tostring),
        ((.llm_used_url//.llm_url//"")|tostring)
      ] | @tsv
    ' "$t" || true
  done
  echo
}

dump_phase3_artifacts() {
  local rid="$1"
  [[ -z "$rid" ]] && return 0
  local root="$STATE/llm2/runs/$rid"
  [[ -d "$root" ]] || return 0

  echo "## PHASE3 ARTIFACTS (rid=$rid)"
  for dom in chatter missions _summary; do
    local d="$root/$dom/phase3"
    [[ -d "$d" ]] || continue
    echo
    echo "### $dom"
    for f in prompt.txt response_text.txt cleaned_text.txt trace.json card.json; do
      if [[ -f "$d/$f" ]]; then
        echo "----- $dom/phase3/$f -----"
        # trace.json can be huge, show short
        if [[ "$f" == "trace.json" ]]; then
          jq '{ok, error, elapsed_ms, llm_url, sent_prompt_bytes:(.sent.prompt_bytes//null), received_text_bytes:(.received.text_bytes//null)}' "$d/$f" 2>/dev/null || cat "$d/$f"
        else
          cat "$d/$f"
        fi
      fi
    done
  done
  echo
}

extract_rid() {
  # Prefer the 16-char Zulu RID like 20260305T142927Z anywhere in stdout
  rg -o '20[0-9]{6}T[0-9]{6}Z' -m 1 || true
}

for n in $(seq "$F" "$T"); do
  PH="phase${n}"
  echo "## RUN $PH"

  # Capture runner output (still print it)
  out="$("$PY" -m takctl.services.llm2.runner --phase "$PH" --once | tee /dev/fd/2)"

  echo
  print_traces "$PH"

  RID="$(printf '%s\n' "$out" | extract_rid)"
  if [[ "$PH" == "phase3" && -n "$RID" ]]; then
    dump_phase3_artifacts "$RID"
  fi
done

echo "## Done"
