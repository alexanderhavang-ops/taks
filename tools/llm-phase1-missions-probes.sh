#!/usr/bin/env bash
set -euo pipefail

# -----------------------------
# CONFIG
# -----------------------------

MODEL_ENDPOINT="${MODEL_ENDPOINT:-http://127.0.0.1:8090/v1/completions}"
MODEL_NAME="${MODEL_NAME:-local-small}"

SYSTEM_FILE="${SYSTEM_FILE:-/opt/taks/llm-infra/llm/prompt-packs/phase1-missions-probes/system.txt}"
USER_FILE="${USER_FILE:-/opt/taks/llm-infra/llm/prompt-packs/phase1-missions-probes/user.txt}"

MAX_PROBES="${MAX_PROBES:-6}"
MAX_ITERS="${MAX_ITERS:-3}"
TEMPERATURE="${TEMPERATURE:-0.2}"
MAX_TOKENS="${MAX_TOKENS:-700}"

OUT_FILE="${OUT_FILE:-/opt/tak/takctl-state/llm/phase1/missions.probes.results.json}"

# -----------------------------
# DB credentials
# -----------------------------

source /opt/tak/tools/takctl/secrets/db.env

DB_HOST="$TAKCTL_DB_HOST"
DB_PORT="$TAKCTL_DB_PORT"
DB_NAME="$TAKCTL_DB_NAME"
DB_USER="$TAKCTL_DB_USER"

export PGPASSWORD="$TAKCTL_DB_PASSWORD"

# -----------------------------
# SCHEMA INTROSPECTION
# -----------------------------

echo "## Introspecting schema..."

SCHEMA_JSON=$(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -Atc "
SELECT json_build_object(
  'schema',
  json_build_object(
    'tables',
    json_agg(
      json_build_object(
        'name', table_name,
        'columns',
        (
          SELECT json_agg(column_name ORDER BY ordinal_position)
          FROM information_schema.columns c2
          WHERE c2.table_schema = 'public'
            AND c2.table_name = c1.table_name
        )
      )
    )
  )
)
FROM (
  SELECT DISTINCT table_name
  FROM information_schema.columns
  WHERE table_schema = 'public'
    AND table_name IN (
      'mission',
      'mission_change',
      'mission_log',
      'mission_invitation'
    )
) c1;
")

echo "## SCHEMA:"
echo "$SCHEMA_JSON"
echo

# -----------------------------
# Build prompt
# -----------------------------

PROMPT=$(cat "$SYSTEM_FILE")
PROMPT+=$'\n'
PROMPT+="$SCHEMA_JSON"

echo "## Calling LLM..."

RAW=$(python3 - <<PY
import json, urllib.request

payload = {
    "model": "$MODEL_NAME",
    "prompt": """$PROMPT""",
    "max_tokens": $MAX_TOKENS,
    "temperature": $TEMPERATURE,
    "stream": False
}

req = urllib.request.Request(
    "$MODEL_ENDPOINT",
    data=json.dumps(payload).encode(),
    headers={"Content-Type": "application/json"}
)

with urllib.request.urlopen(req) as r:
    print(r.read().decode())
PY
)

echo "## RAW RESPONSE:"
echo "$RAW"
echo

TEXT=$(echo "$RAW" | python3 - <<'PY'
import sys, json

raw = sys.stdin.read()
j = json.loads(raw)
print((j.get("choices") or [{}])[0].get("text","").strip())
PY
)

# -----------------------------
# CLEAN JSON RESPONSE
# -----------------------------

CLEAN=$(echo "$TEXT" | python3 - <<'PY'
import sys, re

text = sys.stdin.read()

# Find first JSON object
match = re.search(r'\{.*\}', text, re.DOTALL)
if match:
    print(match.group(0))
else:
    print("")
PY
)

# -----------------------------
# EXECUTE PROBES WITH ITERATION
# -----------------------------

echo "## Executing probes..."

python3 - <<PY
import json, subprocess, os, sys

def sanitize_sql(text: str) -> str:
    t = text.strip()
    t = t.replace("```", "")
    t = t.replace("`", "")
    if t.lower().startswith("sql"):
        t = t[3:].strip()
    if ";" in t:
        t = t.split(";")[0]
    return t.strip() + ";"

def run_sql(sql):
    try:
        out = subprocess.check_output(
            [
                "psql",
                "-h", "$DB_HOST",
                "-p", "$DB_PORT",
                "-U", "$DB_USER",
                "-d", "$DB_NAME",
                "-Atc", sql
            ],
            stderr=subprocess.STDOUT
        ).decode().strip()
        return True, out
    except subprocess.CalledProcessError as e:
        return False, e.output.decode().strip()

def call_fix(sql, error):
    fix_prompt = f"""
You are fixing a PostgreSQL SQL query.

Return ONLY a valid PostgreSQL SELECT statement.
No prose.
No markdown.
No comments.
No backticks.

Schema:
$SCHEMA_JSON

Original SQL:
{sql}

Error:
{error}
"""
    payload = {
        "model": "$MODEL_NAME",
        "prompt": fix_prompt,
        "max_tokens": 300,
        "temperature": 0.1,
        "stream": False
    }

    import urllib.request
    req = urllib.request.Request(
        "$MODEL_ENDPOINT",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as r:
        resp = json.loads(r.read().decode())
        text = (resp.get("choices") or [{}])[0].get("text","")
        return sanitize_sql(text)

data = json.loads("""$CLEAN""")

results = {}

for probe in data.get("probes", [])[:$MAX_PROBES]:

    name = probe["name"]
    original_sql = sanitize_sql(probe["sql"])

    attempts = []
    sql = original_sql

    for attempt in range(1, $MAX_ITERS + 1):
        ok, output = run_sql(sql)

        attempts.append({
            "attempt": attempt,
            "sql": sql,
            "ok": ok,
            "output": output
        })

        if ok:
            break
        else:
            sql = call_fix(sql, output)

    results[name] = {
        "probe": probe,
        "attempts": attempts
    }

print(json.dumps(results, indent=2))

with open("$OUT_FILE", "w") as f:
    json.dump(results, f, indent=2)
PY

echo
echo "Saved results to: $OUT_FILE"

