#!/usr/bin/env bash
set -e

MODEL_ENDPOINT="http://127.0.0.1:8090/v1/completions"
MODEL_NAME="local-small"

STATE_DIR="/opt/tak/takctl-state/llm/phase1"
STATE_FILE="$STATE_DIR/missions.json"

SYSTEM_FILE="/opt/taks/llm-infra/llm/prompt-packs/phase1-missions/system.txt"
USER_FILE="/opt/taks/llm-infra/llm/prompt-packs/phase1-missions/user.txt"

mkdir -p "$STATE_DIR"

PROMPT_FILE="$(mktemp)"
RESP_JSON="$(mktemp)"

# ---- Build schema subset manually (no DB introspection yet) ----
CONTEXT_JSON="$(cat <<'JSON'
{
  "schema": {
    "tables": [
      { "name": "mission", "columns": ["id","name","creatoruid","create_time","groups","chatroom","description","parent_mission_id","expiration","last_edited","invite_only","guid"] },
      { "name": "mission_change", "columns": ["id","mission_name","ts","change_type","mission_id","creatoruid","servertime","mission_guid"] },
      { "name": "mission_log", "columns": ["id","content","creator_uid","dtg","servertime","created"] },
      { "name": "mission_invitation", "columns": ["id","mission_name","invitee","creator_uid","create_time","mission_id","mission_guid"] }
    ]
  },
  "previous_findings": null
}
JSON
)"

# Inject context into user template (multi-line safe)
python3 - "$USER_FILE" "$PROMPT_FILE" "$CONTEXT_JSON" <<'PY'
import sys
tmpl_path, out_path, ctx = sys.argv[1], sys.argv[2], sys.argv[3]
s = open(tmpl_path, "r", encoding="utf-8").read()
s = s.replace("{{CONTEXT_JSON}}", ctx)
open(out_path, "w", encoding="utf-8").write(s)
PY

FULL_PROMPT="$(cat "$SYSTEM_FILE"; echo; cat "$PROMPT_FILE")"

python3 - "$FULL_PROMPT" >"$RESP_JSON" <<'PY'
import json, sys, urllib.request

prompt = sys.argv[1]

payload = {
    "model": "local-small",
    "prompt": prompt,
    "max_tokens": 900,
    "temperature": 0.2,
    "stream": False
}

req = urllib.request.Request(
    "http://127.0.0.1:8090/v1/completions",
    data=json.dumps(payload).encode(),
    headers={"Content-Type":"application/json"}
)

with urllib.request.urlopen(req) as r:
    print(r.read().decode())
PY

echo "=== RAW LLM RESPONSE ==="
cat "$RESP_JSON"
echo

# ---- Extract text ----
TEXT="$(python3 - "$RESP_JSON" <<'PY'
import json, sys
j = json.load(open(sys.argv[1], "r", encoding="utf-8"))
print(((j.get("choices") or [{}])[0] or {}).get("text","").strip())
PY
)"

# If it returns fenced json, strip fences; keep rest intact
CLEAN="$(printf "%s" "$TEXT" | sed -e 's/^[[:space:]]*```json[[:space:]]*$//' -e 's/^[[:space:]]*```[[:space:]]*$//' -e 's/[[:space:]]*```[[:space:]]*$//')"

echo "=== CLEANED TEXT ==="
echo "$CLEAN"
echo

echo "=== VALIDATE JSON ==="
python3 - "$CLEAN" <<'PY'
import json, sys
s = sys.argv[1].strip()
obj = json.loads(s)
required = ["domain","updated_ts_utc","tables","signals","joins","unknowns"]
for k in required:
    if k not in obj:
        raise SystemExit(f"missing key: {k}")
if obj.get("domain") != "tactical.missions":
    raise SystemExit(f"domain mismatch: {obj.get('domain')}")
print("OK JSON.")
PY

echo "$CLEAN" > "$STATE_FILE"

echo
echo "Saved to: $STATE_FILE"

