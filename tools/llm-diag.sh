#!/usr/bin/env bash
set -euo pipefail

# -----------------------------------------------------------------------------
# LLM DIAG: curl + takctl python framework, phased checks, clear output
# -----------------------------------------------------------------------------
# What it does:
#  A) Port ownership + llama presence
#  B) curl tiny prompt
#  C) curl medium prompt
#  D) curl tactical phase2 prompt (from file)
#  E) takctl python tiny prompt
#  F) takctl python tactical phase2 prompt
#
# It prints:
#  - HTTP code, body bytes, finish_reason, extracted text length
#  - whether output contains ``` fences
#  - whether extracted text is valid JSON (+ keys if object)
#
# Env overrides (optional):
#   LLM_EP=http://127.0.0.1:8090/v1/completions
#   LLM_MODEL=local-small
#   PHASE2_PROMPT=/opt/tak/tools/takctl/state/llm/tactical-operations/runs/.../phase2/prompt.txt
#   TAK_PYTHONPATH=/opt/tak/tools/takctl
#
# Note: takctl framework call uses tak user/group.
# -----------------------------------------------------------------------------

EP="${LLM_EP:-http://127.0.0.1:8090/v1/completions}"
MODEL="${LLM_MODEL:-local-small}"
PHASE2_PROMPT="${PHASE2_PROMPT:-/opt/tak/tools/takctl/state/llm/tactical-operations/runs/20260225T211329Z/phase2/prompt.txt}"
TAK_PYTHONPATH="${TAK_PYTHONPATH:-/opt/tak/tools/takctl}"

TS="$(date -u +%Y%m%dT%H%M%SZ)"
D="/tmp/llm-diag.$TS"
mkdir -p "$D"

say() { echo; echo "===================================================================="; echo "$*"; echo "===================================================================="; }
kv()  { printf "%-22s %s\n" "$1:" "$2"; }

url_hostport() {
  # extract host:port from http(s)://host:port/...
  python3 - "$1" <<'PY'
import sys, urllib.parse
u=urllib.parse.urlparse(sys.argv[1])
host=u.hostname or ""
port=u.port or (443 if u.scheme=="https" else 80)
print(f"{host}:{port}")
PY
}

PORT="$(python3 - "$EP" <<'PY'
import sys, urllib.parse
u=urllib.parse.urlparse(sys.argv[1])
print(u.port or (443 if u.scheme=="https" else 80))
PY
)"

HOSTPORT="$(url_hostport "$EP")"

say "0) Inputs"
kv "EP" "$EP"
kv "MODEL" "$MODEL"
kv "PHASE2_PROMPT" "$PHASE2_PROMPT"
kv "ARTIFACT_DIR" "$D"
echo

say "A) Port ownership / process sanity"
echo "## Listener on $HOSTPORT"
sudo ss -ltnp | awk -v p=":$PORT$" '$4 ~ p {print}' || true
echo
echo "## llama-server processes"
pgrep -af '/usr/local/bin/llama-server' || echo "NO llama-server process"
echo
echo "## llm-local.service status (if present)"
sudo systemctl status llm-local.service --no-pager -l 2>/dev/null | sed -n '1,120p' || true

# -------------------------
# Helpers: curl call + parse
# -------------------------
mk_req_file() {
  local prompt_file="$1"
  local out="$2"
  local max_tokens="$3"
  python3 - "$prompt_file" "$MODEL" "$max_tokens" >"$out" <<'PY'
import json,sys
from pathlib import Path
pf=sys.argv[1]
model=sys.argv[2]
max_tokens=int(sys.argv[3])
p=Path(pf).read_text(encoding="utf-8", errors="replace")
sys.stdout.write(json.dumps({
  "model": model,
  "prompt": p,
  "max_tokens": max_tokens,
  "temperature": 0.0,
  "stream": False
}, ensure_ascii=False))
PY
}

parse_openai_body() {
  local body="$1"
  python3 - "$body" <<'PY'
import json,sys
from pathlib import Path

raw = Path(sys.argv[1]).read_bytes()
try:
    o = json.loads(raw.decode("utf-8","replace"))
except Exception as e:
    print("BODY_JSON_PARSE: FAIL", str(e))
    print("BODY_HEAD200_PRINTABLE:")
    head = raw[:200].decode("utf-8","replace")
    print("".join((c if c.isprintable() or c in "\t\n\r" else ".") for c in head))
    sys.exit(0)

keys = sorted(list(o.keys()))
print("BODY_JSON_PARSE: OK")
print("TOP_KEYS:", keys)

choices = (o.get("choices") or [])
c0 = (choices[0] if choices else {}) or {}
t = (c0.get("text") or "")
fr = c0.get("finish_reason")
print("finish_reason:", fr)
print("text_len:", len(t))
print("has_backticks:", ("```" in t))

# JSON check on extracted text
try:
    j = json.loads(t)
    ok = True
except Exception as e:
    ok = False
    err = str(e)

print("extracted_json_ok:", ok)
if ok and isinstance(j, dict):
    print("extracted_json_keys:", sorted(list(j.keys())))
elif ok:
    print("extracted_json_type:", type(j).__name__)
else:
    print("extracted_json_error:", err)

print("---- extracted choices[0].text (verbatim) ----")
print(t)
PY
}

curl_run() {
  local label="$1"
  local prompt_file="$2"
  local max_tokens="$3"

  local req="$D/${label}.curl.req.json"
  local hdr="$D/${label}.curl.hdr.txt"
  local body="$D/${label}.curl.body.bin"

  mk_req_file "$prompt_file" "$req" "$max_tokens"

  say "CURL :: $label"
  kv "REQ_BYTES" "$(wc -c <"$req")"
  kv "REQ_SHA256" "$(sha256sum "$req" | awk '{print $1}')"
  kv "PROMPT_BYTES" "$(wc -c <"$prompt_file")"
  kv "PROMPT_SHA256" "$(sha256sum "$prompt_file" | awk '{print $1}')"

  code="$(curl -sS --max-time 600 -D "$hdr" -o "$body" -w '%{http_code}' \
    -H 'content-type: application/json' \
    --data-binary @"$req" \
    "$EP" || true)"

  echo
  kv "HTTP_CODE" "$code"
  kv "BODY_BYTES" "$(wc -c <"$body")"
  echo
  echo "--- response headers (first 40 lines) ---"
  sed -n '1,40p' "$hdr" || true
  echo
  parse_openai_body "$body"
}

# -------------------------
# Helpers: takctl framework call
# -------------------------
py_run() {
  local label="$1"
  local prompt_file="$2"
  local max_tokens="$3"

  local dump="$D/${label}.py.dump"
  sudo rm -rf "$dump"
  sudo mkdir -p "$dump"
  sudo chown tak:tak "$dump"

  say "PY(takctl) :: $label"
  kv "PROMPT_FILE" "$prompt_file"
  kv "PROMPT_BYTES" "$(wc -c <"$prompt_file")"
  kv "PROMPT_SHA256" "$(sha256sum "$prompt_file" | awk '{print $1}')"
  kv "DUMP_DIR" "$dump"
  echo

  # This prints:
  #  - http code + err
  #  - body json keys
  #  - extracted text + checks (same as curl)
  sudo -u tak -g tak env \
    PYTHONPATH="$TAK_PYTHONPATH" \
    TAKS_LLM_HTTP_DUMP_DIR="$dump" \
    LLM_URL="$EP" \
    python3 - "$prompt_file" "$MODEL" "$max_tokens" <<'PY'
import json, os, sys
from pathlib import Path

from takctl.services.llm_http import http_post_json

prompt_file = sys.argv[1]
model = sys.argv[2]
max_tokens = int(sys.argv[3])

p = Path(prompt_file).read_text(encoding="utf-8", errors="replace")
payload = {
  "model": model,
  "prompt": p,
  "max_tokens": max_tokens,
  "temperature": 0.0,
  "stream": False,
}

url = os.environ.get("LLM_URL") or "http://127.0.0.1:8090/v1/completions"
code, body, err = http_post_json(url, payload, timeout_sec=600.0)

print("HTTP_CODE:", code)
print("ERR:", err)

if not isinstance(body, dict):
    print("BODY_TYPE:", type(body).__name__)
    print("BODY_REPR:", repr(body)[:5000])
    sys.exit(0)

print("TOP_KEYS:", sorted(list(body.keys())))
choices = (body.get("choices") or [])
c0 = (choices[0] if choices else {}) or {}
t = (c0.get("text") or "")
fr = c0.get("finish_reason")
print("finish_reason:", fr)
print("text_len:", len(t))
print("has_backticks:", ("```" in t))

try:
    j = json.loads(t)
    ok = True
except Exception as e:
    ok = False
    err2 = str(e)

print("extracted_json_ok:", ok)
if ok and isinstance(j, dict):
    print("extracted_json_keys:", sorted(list(j.keys())))
elif ok:
    print("extracted_json_type:", type(j).__name__)
else:
    print("extracted_json_error:", err2)

print("---- extracted choices[0].text (verbatim) ----")
print(t)
PY

  echo
  echo "Dump artifacts:"
  ls -lah "$dump" | sed -n '1,200p' || true
}

# -------------------------
# Prompt files
# -------------------------
TRIV="$D/prompt.trivial.txt"
MED="$D/prompt.medium.txt"

cat >"$TRIV" <<'EOF'
Return exactly: {"ok":true}
Rules:
- JSON only
- no backticks, no code fences, no prose
EOF

cat >"$MED" <<'EOF'
You are a strict JSON generator.

Return ONLY valid JSON (no prose, no markdown, no code fences).

JSON shape:
{
  "status": "ok",
  "numbers": [1,2,3],
  "note": "short"
}

Now output the JSON object.
EOF

if [ ! -f "$PHASE2_PROMPT" ]; then
  say "ERROR: phase2 prompt file missing"
  echo "Missing: $PHASE2_PROMPT"
  echo "Set PHASE2_PROMPT=... and rerun."
  exit 2
fi

# -------------------------
# Run phases
# -------------------------
say "B) CURL phases (direct to llama OpenAI endpoint)"
curl_run "curl.1.trivial" "$TRIV" 64
curl_run "curl.2.medium" "$MED" 128
curl_run "curl.3.phase2" "$PHASE2_PROMPT" 450

say "C) PY phases (through takctl.services.llm_http.http_post_json)"
py_run "py.1.trivial" "$TRIV" 64
py_run "py.2.phase2" "$PHASE2_PROMPT" 450

say "DONE"
echo "Artifacts: $D"
echo "If something fails, paste the whole section output + the artifact dir listing."
