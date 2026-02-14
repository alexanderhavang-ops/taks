#!/usr/bin/env bash
set -euo pipefail

DB_HOST="${DB_HOST:-127.0.0.1}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-cot}"

# Use env if set; otherwise fall back to whatever takctl uses.
DB_USER="${DB_USER:-takctl_crl_ro}"

MODEL="${MODEL:-local-small}"
LLM_URL="${LLM_URL:-http://127.0.0.1:8090}"

PROMPT_FILE="$(mktemp)"
RESPONSE_FILE="$(mktemp)"
SCHEMA_FILE="$(mktemp)"

cleanup() { rm -f "$PROMPT_FILE" "$RESPONSE_FILE" "$SCHEMA_FILE"; }
trap cleanup EXIT

echo "=== 1) DUMPING COMPACT SCHEMA (public schemas, tables/views) ==="
psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -Atc "
WITH cols AS (
  SELECT
    n.nspname AS schema,
    c.relname AS name,
    a.attnum,
    a.attname
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
  JOIN pg_attribute a ON a.attrelid = c.oid
  WHERE c.relkind IN ('r','v','m','p')
    AND a.attnum > 0
    AND NOT a.attisdropped
    AND n.nspname NOT IN ('pg_catalog','information_schema')
)
SELECT schema || '.' || name || ': ' ||
       string_agg(attname, ', ' ORDER BY attnum)
FROM cols
GROUP BY schema, name
ORDER BY schema, name;
" > "$SCHEMA_FILE"

echo "Schema lines: $(wc -l < "$SCHEMA_FILE")"
echo

echo "=== 2) BUILD PROMPT ==="
cat >"$PROMPT_FILE" <<EOF
You are part of a programmatic interface.

Return EXACTLY one JSON object on a single line with EXACTLY this shape:
{"sql":"..."}

Rules:
- Only key allowed: sql
- Must be valid JSON
- No prose, no markdown, no code fences, no examples, no extra characters

SQL constraints:
- Must start with SELECT or WITH
- Single statement only
- No semicolons
- Read-only only
- Prefer stable output columns: use AS <alias> for returned expressions
- Add LIMIT when returning rows
- Use ONLY tables/columns that exist in the schema below

SCHEMA (schema.table: columns...):
$(sed -n '1,400p' "$SCHEMA_FILE")

TASK:
Given this TAK Server database schema, propose ONE useful SQL query that helps answer:
"Tactical situation summary: what has changed most recently?"
The query should produce a small, human-readable result suitable for a tactical dashboard.

Return ONLY the JSON object.
EOF

echo "----- PROMPT (first 120 lines) -----"
sed -n '1,120p' "$PROMPT_FILE"
echo "----- (prompt truncated) -----"
echo

echo "=== 3) CALL LLM ==="
python3 - "$PROMPT_FILE" >"$RESPONSE_FILE" <<'PY'
import json, sys, urllib.request

prompt = open(sys.argv[1], "r", encoding="utf-8").read()

payload = {
  "model": "local-small",
  "prompt": prompt,
  "max_tokens": 200,
  "temperature": 0.2,
  "stream": False,
}

req = urllib.request.Request(
  "http://127.0.0.1:8090/v1/completions",
  data=json.dumps(payload).encode("utf-8"),
  headers={"content-type":"application/json"},
  method="POST",
)

with urllib.request.urlopen(req, timeout=120) as r:
  sys.stdout.write(r.read().decode("utf-8"))
PY

echo "=== RAW RESPONSE JSON ==="
python3 -m json.tool < "$RESPONSE_FILE" | sed -n '1,120p'
echo

echo "=== EXTRACTED TEXT (raw) ==="
python3 - "$RESPONSE_FILE" <<'PY'
import json, sys, re
b=json.load(open(sys.argv[1]))
t=((b.get("choices") or [{}])[0] or {}).get("text","")
print(t)
PY
echo

echo "=== CANDIDATE JSON (best-effort strip fences/whitespace) ==="
CANDIDATE="$(python3 - "$RESPONSE_FILE" <<'PY'
import json, sys, re
b=json.load(open(sys.argv[1]))
t=((b.get("choices") or [{}])[0] or {}).get("text","").strip()

# strip ```json ... ``` or ``` ... ```
m = re.search(r"\{.*\}", t, flags=re.S)
if m:
    print(m.group(0).strip())
else:
    print(t)
PY
)"
echo "$CANDIDATE"
echo

echo "=== VALIDATE CANDIDATE ==="
python3 - <<PY
import json, sys
s = """$CANDIDATE""".strip()
obj = json.loads(s)
if set(obj.keys()) != {"sql"} or not isinstance(obj["sql"], str):
    raise SystemExit(f"BAD SHAPE: keys={list(obj.keys())} sql_type={type(obj.get('sql'))}")
print("OK JSON. sql =", obj["sql"])
PY
