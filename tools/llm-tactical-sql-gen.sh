#!/usr/bin/env bash
set -e

LLM_URL="${LLM_URL:-http://127.0.0.1:8090}"
MODEL="${MODEL:-local-small}"

PROMPT_FILE="$(mktemp)"
RESP_JSON="$(mktemp)"
SQL_FILE="$(mktemp)"

cleanup() {
  # Keep on failure (we explicitly keep below when we error)
  rm -f "$PROMPT_FILE" "$RESP_JSON" "$SQL_FILE" 2>/dev/null || true
}
trap cleanup EXIT

cat >"$PROMPT_FILE" <<'EOF'
You are part of a programmatic interface.

Return EXACTLY one JSON object on a single line with EXACTLY this shape:
{"sql":"..."}

Rules:
- Only key allowed: sql
- Must be valid JSON with double quotes
- No prose, no markdown, no code fences, no extra characters before/after JSON
- If you cannot comply, return exactly: {"sql":""}
- NEVER output placeholder SQL like SELECT ... or ... or SELECT 1
- SQL must be ONE read-only statement (SELECT or WITH), and MUST NOT end with a semicolon.

TASK:
Given the schema below, propose ONE SQL query that returns a compact "tactical snapshot" (multiple rows) suitable for a dashboard.

Return rows with columns:
  section, metric, value, ts_utc

Guidance:
- Use UNION ALL to combine rows.
- section: category like clients/missions/events/feeds/federation/errors
- metric: what the row measures
- value: cast to text
- ts_utc: timestamp (use NOW() if needed)
- Keep it cheap: counts + max timestamps.
- Avoid scanning large blobs (certificate/detail/xml/image/data columns).

SCHEMA (tables and columns):
active_group_cache: id, username, groupname, direction, enabled
certificate: id, creator_dn, subject_dn, user_dn, issuance_date, effective_date, expiration_date, revocation_date, certificate, hash, client_uid, token
client_endpoint: id, callsign, uid, username
client_endpoint_event: id, client_endpoint_id, connection_event_type_id, created_ts, client_version, groups
connection_event_type: id, event_name
cot_router: id, uid, cot_type, access, qos, opex, start, time, stale, how, point_hae, point_ce, point_le, detail, servertime, servertime_hour, event_pt, groups, caveat, releaseableto
cot_router_chat: id, uid, cot_type, access, qos, opex, start, time, stale, how, point_hae, point_ce, point_le, groups, detail, servertime, sender_callsign, dest_callsign, dest_uid, chat_content, chat_room, event_pt
data_feed: id, uuid, name, type, auth, port, auth_required, protocol, feed_group, iface, archive, anongroup, sync, archive_only, core_version, core_version_tls_versions, groups, sync_cache_retention_seconds, federated, binary_payload_websocket_only, predicate_lang, data_source_endpoint, predicate, auth_type
fed_event: fed_id, fed_name, event_kind_id, event_time, remote, details
error_logs: id, uid, callsign, log, time, filename, major_version, minor_version, platform, contents
latestcot: id, uid, cot_type, access, qos, opex, start, time, stale, how, point_hae, point_ce, point_le, detail, servertime, event_pt
latestresource: id, altitude, data, filename, keywords, location, mimetype, name, permissions, remarks, submissiontime, submitter, uid, hash, groups, tool
mission: id, name, creatoruid, create_change_id, create_time, tool, groups, chatroom, description, parent_mission_id, password_hash, default_role_id, expiration, base_layer, bbox, path, classification, last_edited, bounding_polygon, invite_only, guid
mission_change: id, hash, uid, mission_name, ts, change_type, mission_id, creatoruid, external_data_token, external_data_name, external_data_tool, external_data_uid, external_data_notes, servertime, mission_feed_uid, map_layer_uid, remote_federated_change, xml_content_for_notification, mission_guid
mission_invitation: id, mission_name, invitee, type, creator_uid, create_time, token, role_id, mission_id, mission_guid
mission_log: id, content, creator_uid, dtg, entry_uid, servertime, created

Return ONLY the JSON object.
EOF

# Send to llama-server
python3 - "$PROMPT_FILE" "$RESP_JSON" <<'PY'
import json, sys, urllib.request

prompt = open(sys.argv[1], "r", encoding="utf-8").read()

payload = {
  "model": "local-small",
  "prompt": prompt,
  "max_tokens": 700,
  "temperature": 0.2,
  "stream": False
}

req = urllib.request.Request(
  "http://127.0.0.1:8090/v1/completions",
  data=json.dumps(payload).encode("utf-8"),
  headers={"content-type":"application/json"},
  method="POST",
)
with urllib.request.urlopen(req, timeout=600) as r:
  body = r.read().decode("utf-8", errors="replace")

open(sys.argv[2], "w", encoding="utf-8").write(body)
PY

echo "=== RAW RESPONSE JSON ==="
python3 -m json.tool < "$RESP_JSON" || true
echo

# Extract last valid {"sql":"..."} from the model's *text* field
python3 - "$RESP_JSON" "$SQL_FILE" <<'PY'
import json, re, sys

resp = json.load(open(sys.argv[1], "r", encoding="utf-8"))
text = str((((resp.get("choices") or [{}])[0] or {}).get("text")) or "")

# Remove common code fences to make JSON detection easier
text2 = text.replace("```json", "```").replace("```sql", "```")

# Find ALL json-ish objects and keep those that parse to {"sql": "..."} only
cands = []
for m in re.finditer(r"\{[\s\S]*?\}", text2):
    s = m.group(0).strip()
    # quick skip if no "sql"
    if '"sql"' not in s:
        continue
    try:
        obj = json.loads(s)
    except Exception:
        continue
    if isinstance(obj, dict) and set(obj.keys()) == {"sql"} and isinstance(obj["sql"], str):
        sql = obj["sql"].strip()
        cands.append(sql)

sql = (cands[-1].strip() if cands else "")

# Normalize / sanitize
sql = re.sub(r"^\s*```[\s\S]*?\n", "", sql).strip()
sql = re.sub(r"\n```?\s*$", "", sql).strip()
sql = re.sub(r"\s+", " ", sql).strip()
sql = sql.rstrip(";").strip()

# Reject placeholders / empty / non-readonly
bad = False
if not sql:
    bad = True
if "..." in sql:
    bad = True
if not re.match(r"^(select|with)\b", sql, flags=re.I):
    bad = True
if ";" in sql:
    bad = True

open(sys.argv[2], "w", encoding="utf-8").write(sql + "\n")

if bad:
    print(f"Could not extract acceptable sql. sql={sql!r}")
    sys.exit(2)

print("OK extracted sql:", sql)
PY

echo
echo "=== SQL FROM LLM (sanitized) ==="
cat "$SQL_FILE"
echo

echo "=== DB RESULT (first 80 lines) ==="
psql -h 127.0.0.1 -p 5432 -U takctl_crl_ro -d cot -v ON_ERROR_STOP=1 \
  -c "$(cat "$SQL_FILE")" 2>&1 | sed -n '1,80p' || {
    echo
    echo "!! kept debug files:"
    echo "   PROMPT_FILE=$PROMPT_FILE"
    echo "   RESP_JSON=$RESP_JSON"
    echo "   SQL_FILE=$SQL_FILE"
    trap - EXIT
    exit 1
  }
