#!/usr/bin/env bash
set -e

cd /opt/taks

PROMPT_FILE="$(mktemp)"
RESPONSE_FILE="$(mktemp)"
trap 'rm -f "$PROMPT_FILE" "$RESPONSE_FILE"' EXIT

cat >"$PROMPT_FILE" <<'EOF'
You are part of a programmatic interface.

You MUST output exactly ONE JSON object on a single line.
No prose. No markdown. No examples. No code fences. No extra characters.

The JSON format is EXACTLY:
{"sql":"..."}
- Only key allowed: sql
- Value must be a SQL string, or empty string if you cannot comply.

If you output anything other than valid JSON, it will be discarded as an error.

SQL rules:
- Read-only only: must start with SELECT or WITH
- Single statement only
- No semicolons
- No writes / DDL / COPY
- Do NOT return placeholder SQL like SELECT 1 / SELECT true / SELECT now()
- Prefer stable output columns: use AS <alias> for returned expressions
- Add LIMIT when returning rows (not needed for version()).

User question:
What is the database version? Return the answer.

Return ONLY the JSON object.
EOF

echo "----- PROMPT BEGIN -----"
cat "$PROMPT_FILE"
echo "----- PROMPT END -----"
echo

python3 - "$PROMPT_FILE" "$RESPONSE_FILE" <<'PY'
import json, sys, urllib.request, re

prompt_path, resp_path = sys.argv[1], sys.argv[2]
prompt = open(prompt_path, "r", encoding="utf-8").read()

payload = {
    "model": "local-small",
    "prompt": prompt,
    "max_tokens": 120,
    "temperature": 0.0,
    "stream": False,
    # IMPORTANT: no "stop" here (it can stop on the very first newline)
}

req = urllib.request.Request(
    "http://127.0.0.1:8090/v1/completions",
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)

with urllib.request.urlopen(req, timeout=120) as r:
    body = r.read().decode("utf-8", errors="replace")

open(resp_path, "w", encoding="utf-8").write(body)

# Pretty print raw response JSON
print("=== RAW RESPONSE JSON ===")
try:
    print(json.dumps(json.loads(body), indent=2))
except Exception:
    print(body)

# Extract model text
obj = json.loads(body)
text = str(((obj.get("choices") or [{}])[0] or {}).get("text") or "")
print("\n=== EXTRACTED TEXT (raw) ===")
print(text)

# Find first JSON object in text (best-effort)
m = re.search(r'\{.*\}', text, flags=re.S)
candidate = (m.group(0).strip() if m else text.strip())

print("\n=== CANDIDATE JSON ===")
print(candidate)

print("\n=== VALIDATE CANDIDATE ===")
try:
    j = json.loads(candidate)
except Exception as e:
    raise SystemExit(f"NOT JSON: {e}\nCANDIDATE={candidate!r}")

if set(j.keys()) != {"sql"} or not isinstance(j["sql"], str):
    raise SystemExit(f"BAD SHAPE: keys={list(j.keys())}, sql_type={type(j.get('sql'))}")

print("OK JSON. sql =", j["sql"])
PY
