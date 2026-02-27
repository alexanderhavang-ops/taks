#!/usr/bin/env bash
set -euo pipefail

LLM_URL_DEFAULT="http://127.0.0.1:8090"
PHASE2_DEFAULT="/opt/tak/tools/takctl/state/llm/tactical-operations/runs/20260225T211329Z/phase2/prompt.txt"
UNIT_DEFAULT="llm-local.service"

LLM_URL="${TAKS_LLM_URL:-$LLM_URL_DEFAULT}"
PHASE2_PROMPT="${1:-$PHASE2_DEFAULT}"
UNIT="${TAKS_LLM_SYSTEMD_UNIT:-$UNIT_DEFAULT}"

TS="$(date -u +%Y%m%dT%H%M%SZ)"
D="/tmp/taks-llm-smoketest.$TS"
mkdir -p "$D"

say() { echo; echo "============================================================"; echo "$*"; echo "============================================================"; }

have() { command -v "$1" >/dev/null 2>&1; }

req_curl_completion() {
  local label="$1"
  local prompt_file="$2"
  local max_tokens="${3:-128}"
  local req="$D/${label}.req.json"
  local hdr="$D/${label}.hdr.txt"
  local body="$D/${label}.body.bin"

  python3 - "$prompt_file" "$max_tokens" >"$req" <<'PY'
import json,sys
from pathlib import Path
p = Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace")
max_tokens = int(sys.argv[2])
sys.stdout.write(json.dumps({
  "model":"local-small",
  "prompt": p,
  "max_tokens": max_tokens,
  "temperature": 0.0,
  "stream": False
}, ensure_ascii=False))
PY

  local code
  code="$(curl -sS --max-time 600 -D "$hdr" -o "$body" -w '%{http_code}' \
    -H 'content-type: application/json' \
    --data-binary @"$req" \
    "$LLM_URL/v1/completions" || true)"

  echo "LABEL=$label"
  echo "URL=$LLM_URL/v1/completions"
  echo "REQ_BYTES=$(wc -c <"$req") REQ_SHA256=$(sha256sum "$req" | awk '{print $1}')"
  echo "HTTP_CODE=$code BODY_BYTES=$(wc -c <"$body")"
  echo "--- response headers (first 30 lines) ---"
  sed -n '1,30p' "$hdr" || true

  python3 - "$body" <<'PY'
import json,sys
from pathlib import Path

raw = Path(sys.argv[1]).read_bytes()
try:
    o = json.loads(raw.decode("utf-8","replace"))
except Exception as e:
    print("RESPONSE_NOT_JSON:", e)
    print("RAW_BODY_VERBATIM_START")
    sys.stdout.flush()
    try:
        sys.stdout.buffer.write(raw)
        if not raw.endswith(b"\n"):
            sys.stdout.buffer.write(b"\n")
    except Exception:
        pass
    print("RAW_BODY_VERBATIM_END")
    raise SystemExit(0)

t = ""
try:
    t = str((((o.get("choices") or [{}])[0]) or {}).get("text") or "")
except Exception:
    t = ""

print("---- choices[0].text (verbatim) ----")
print(t)
print("---- checks ----")
print("has_backticks:", "```" in t)
try:
    j = json.loads(t)
    print("json_ok: True")
    if isinstance(j, dict):
        print("json_keys:", sorted(list(j.keys())))
    else:
        print("json_type:", type(j).__name__)
except Exception as e:
    print("json_ok: False", str(e))
PY
}

req_py_framework() {
  local label="$1"
  local prompt_file="$2"
  local max_tokens="${3:-128}"
  local out="$D/${label}.py.json"

  # We run from /opt/taks to ensure imports resolve the same way you normally run takctl code.
  ( cd /opt/taks && python3 - "$LLM_URL" "$prompt_file" "$max_tokens" >"$out" <<'PY'
import json,sys
from pathlib import Path

llm_url = sys.argv[1]
pfile = sys.argv[2]
max_tokens = int(sys.argv[3])
prompt = Path(pfile).read_text(encoding="utf-8", errors="replace")

from takctl.services.llm_raw import llm_completion

res = llm_completion(
    llm_url=llm_url,
    prompt=prompt,
    model="local-small",
    max_tokens=max_tokens,
    temperature=0.0,
    timeout_sec=180.0,
)

# Print a structured summary, then the verbatim text.
print("PY_FRAMEWORK_RESULT_JSON_START")
print(json.dumps({
    "ok": bool(res.get("ok")),
    "status_code": res.get("status_code"),
    "error": res.get("error"),
    "text_len": len((res.get("text") or "")),
}, ensure_ascii=False, indent=2))
print("PY_FRAMEWORK_RESULT_JSON_END")

t = (res.get("text") or "")
print("---- choices[0].text (verbatim) ----")
print(t)

print("---- checks ----")
print("has_backticks:", "```" in t)
try:
    j = json.loads(t)
    print("json_ok: True")
    if isinstance(j, dict):
        print("json_keys:", sorted(list(j.keys())))
    else:
        print("json_type:", type(j).__name__)
except Exception as e:
    print("json_ok: False", str(e))
PY
  )

  echo "LABEL=$label"
  echo "OUT=$out (saved)"
  cat "$out"
}

say "0) Context + ownership"
echo "TS=$TS"
echo "ARTIFACT_DIR=$D"
echo "LLM_URL=$LLM_URL"
echo "UNIT=$UNIT"
echo "PHASE2_PROMPT=$PHASE2_PROMPT"
if [ -f "$PHASE2_PROMPT" ]; then
  echo "PHASE2_BYTES=$(wc -c <"$PHASE2_PROMPT") PHASE2_SHA256=$(sha256sum "$PHASE2_PROMPT" | awk '{print $1}')"
else
  echo "PHASE2_PROMPT_MISSING=1"
fi
echo

echo "## Listener on :8090"
sudo ss -ltnp | awk '$4 ~ /:8090$/ {print}' || true
echo

echo "## systemd status ($UNIT)"
sudo systemctl status "$UNIT" --no-pager -l | sed -n '1,120p' || true

say "1) HTTP health probes (curl)"
echo "## GET /health"
curl -sS -D - -o "$D/health.body" --max-time 5 "$LLM_URL/health" || true
echo
echo "--- /health body (verbatim) ---"
cat "$D/health.body" 2>/dev/null || true
echo
echo "## GET /v1/models"
curl -sS -D - -o "$D/models.body" --max-time 5 "$LLM_URL/v1/models" || true
echo
echo "--- /v1/models body (verbatim) ---"
cat "$D/models.body" 2>/dev/null || true
echo

say "2) curl: trivial completion"
TRIV="$D/trivial.prompt.txt"
cat >"$TRIV" <<'EOF'
Return exactly: {"ok":true}
JSON only. NO backticks. NO code fences.
EOF
req_curl_completion "curl.trivial" "$TRIV" 64

say "3) curl: medium completion"
MED="$D/medium.prompt.txt"
cat >"$MED" <<'EOF'
Return a JSON object with keys:
- ok: true
- msg: a short sentence about the weather
JSON only. NO backticks. NO code fences.
EOF
req_curl_completion "curl.medium" "$MED" 96

say "4) curl: phase2 tactical completion"
if [ -f "$PHASE2_PROMPT" ]; then
  req_curl_completion "curl.phase2" "$PHASE2_PROMPT" 450
else
  echo "SKIP: phase2 prompt file missing: $PHASE2_PROMPT"
fi

say "5) python framework: trivial completion"
req_py_framework "py.trivial" "$TRIV" 64

say "6) python framework: phase2 tactical completion"
if [ -f "$PHASE2_PROMPT" ]; then
  req_py_framework "py.phase2" "$PHASE2_PROMPT" 450
else
  echo "SKIP: phase2 prompt file missing: $PHASE2_PROMPT"
fi

say "DONE"
echo "Artifacts saved in: $D"
ls -lah "$D" | sed -n '1,200p'
