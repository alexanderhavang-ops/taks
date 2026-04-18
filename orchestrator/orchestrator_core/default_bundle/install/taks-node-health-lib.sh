#!/usr/bin/env bash
set -euo pipefail

log() {
  printf '[taks-node-health] %s\n' "$*"
}

read_simple_kv() {
  local path="$1"
  local key="$2"
  [ -f "$path" ] || return 1
  sed -n "s/^[[:space:]]*${key}[[:space:]]*=[[:space:]]*//p" "$path" | head -n 1 | sed -e 's/[[:space:]]*$//'
}

read_kv_first_hit_in_dir() {
  local dir="$1"
  local key="$2"
  [ -d "$dir" ] || return 1
  local f v
  for f in "$dir"/*.conf; do
    [ -f "$f" ] || continue
    v="$(read_simple_kv "$f" "$key" || true)"
    if [ -n "${v:-}" ]; then
      printf '%s' "$v"
      return 0
    fi
  done
  return 1
}

strip_wrapping_quotes() {
  local s="${1:-}"
  s="$(printf '%s' "$s" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
  case "$s" in
    \"*\") s="${s#\"}"; s="${s%\"}" ;;
    \'*\') s="${s#\'}"; s="${s%\'}" ;;
  esac
  printf '%s' "$s"
}

read_secret_first_hit() {
  local key="$1"
  local v=""

  v="$(read_kv_first_hit_in_dir /opt/tak/tools/takctl/secrets.d "$key" || true)"
  if [ -z "$v" ]; then
    v="$(read_kv_first_hit_in_dir /etc/taks-bootstrap.d/secrets.d "$key" || true)"
  fi

  strip_wrapping_quotes "$v"
}

read_trimmed_file() {
  local p="$1"
  [ -f "$p" ] || return 1
  tr -d '\r' < "$p" | sed -e 's/[[:space:]]*$//' | head -n 1
}

get_fqdn() {
  local fqdn=""
  fqdn="$(read_simple_kv "$NODE_CONF" node_fqdn || true)"
  if [ -z "$fqdn" ]; then
    fqdn="$(read_simple_kv "$NODE_CONF" fqdn || true)"
  fi
  printf '%s' "$fqdn"
}

sanitize() {
  tr '\n' ' ' | tr '\t' ' ' | sed 's/  */ /g; s/^ //; s/ $//'
}

add_check() {
  local name="$1"
  local status="$2"
  local severity="$3"
  local summary="$4"
  local extra="${5:-{}}"
  summary="$(printf '%s' "$summary" | sanitize)"
  printf '%s\t%s\t%s\t%s\t%s\n' "$name" "$status" "$severity" "$summary" "$extra" >> "$CHECKS_TSV"
}

service_state() {
  local name="$1"
  systemctl is-active "$name" 2>/dev/null || true
}

service_enabled_state() {
  local name="$1"
  systemctl is-enabled "$name" 2>/dev/null || true
}

port_tcp_listening() {
  local port="$1"
  ss -ltn "( sport = :$port )" 2>/dev/null | tail -n +2 | grep -q .
}

port_udp_listening() {
  local port="$1"
  ss -lun "( sport = :$port )" 2>/dev/null | tail -n +2 | grep -q .
}

http_code() {
  local url="$1"; shift
  curl --silent --show-error --output /dev/null --write-out '%{http_code}' --max-time 8 "$@" "$url" 2>/dev/null || true
}

http_code_insecure() {
  local url="$1"; shift
  curl -k --silent --show-error --output /dev/null --write-out '%{http_code}' --max-time 8 "$@" "$url" 2>/dev/null || true
}

have_admin_identity() {
  local d="/opt/tak/tools/takctl/state/admin_identity"
  [ -d "$d" ] || return 1
  local pem
  pem="$(find "$d" -maxdepth 1 -type f -name '*.pem' ! -name 'ca.pem' | head -n 1 || true)"
  [ -n "$pem" ] || return 1
  [ -f "${pem%.pem}.key" ] || return 1
  [ -f "$d/ca.pem" ] || return 1
  return 0
}

admin_pem() {
  find /opt/tak/tools/takctl/state/admin_identity -maxdepth 1 -type f -name '*.pem' ! -name 'ca.pem' | head -n 1 || true
}

admin_key() {
  local pem
  pem="$(admin_pem)"
  [ -n "$pem" ] && printf '%s' "${pem%.pem}.key" || true
}

admin_ca() {
  printf '%s' "/opt/tak/tools/takctl/state/admin_identity/ca.pem"
}

client_key_passphrase() {
  local v=""
  v="$(read_secret_first_hit cert_pass || true)"
  if [ -z "$v" ]; then
    v="$(read_trimmed_file /etc/taks/certs/PASS || true)"
  fi
  printf '%s' "$v"
}

check_takserver_service() {
  local st
  st="$(service_state takserver.service)"
  if [ "$st" = "active" ] || [ "$st" = "exited" ]; then
    add_check takserver_service ok critical "takserver.service active"
  else
    add_check takserver_service fail critical "takserver.service state=$st"
  fi
}

check_postgres() {
  local st
  st="$(service_state postgresql.service)"
  if [ "$st" = "active" ]; then
    add_check postgres ok critical "postgresql.service active"
  else
    add_check postgres fail critical "postgresql.service state=$st"
  fi
}

check_disk_root() {
  local used
  used="$(df -P / | awk 'NR==2{gsub("%","",$5); print $5}')"
  if [ -z "$used" ]; then
    add_check disk_root warn critical "/ usage unknown"
    return
  fi
  if [ "$used" -ge 95 ]; then
    add_check disk_root fail critical "/ ${used}% used" "{\"used_pct\": $used}"
  elif [ "$used" -ge 85 ]; then
    add_check disk_root warn critical "/ ${used}% used" "{\"used_pct\": $used}"
  else
    add_check disk_root ok critical "/ ${used}% used" "{\"used_pct\": $used}"
  fi
}

check_80() {
  if port_tcp_listening 80; then
    add_check http_80 ok info "port 80 listening"
  else
    add_check http_80 skip info "port 80 not listening"
  fi
}

check_takctl_enabled() {
  local st
  st="$(service_enabled_state takctl-web.service)"
  if [ "$st" = "enabled" ]; then
    add_check takctl_enabled ok critical "takctl-web.service enabled"
  else
    add_check takctl_enabled fail critical "takctl-web.service is-enabled=$st"
  fi
}

check_takctl_active() {
  local st
  st="$(service_state takctl-web.service)"
  if [ "$st" = "active" ]; then
    add_check takctl_active ok critical "takctl-web.service active"
  else
    add_check takctl_active fail critical "takctl-web.service state=$st"
  fi
}

check_takctl_8080_local() {
  if ! port_tcp_listening 8080; then
    add_check takctl_8080_local fail critical "127.0.0.1:8080 not listening"
    return
  fi
  local code
  code="$(http_code "http://127.0.0.1:8080/api/health")"
  if [ "$code" = "200" ]; then
    add_check takctl_8080_local ok critical "127.0.0.1:8080 /api/health returned 200" "{\"http_code\": 200}"
  else
    add_check takctl_8080_local fail critical "127.0.0.1:8080 /api/health http_code=$code" "{\"http_code\": \"${code:-000}\"}"
  fi
}

check_443_health() {
  local fqdn="$1"
  if [ -z "$fqdn" ]; then
    add_check takctl_443 warn critical "fqdn missing"
    return
  fi
  local code
  code="$(http_code "https://$fqdn/api/health" --resolve "$fqdn:443:127.0.0.1")"
  if [ "$code" = "200" ]; then
    add_check takctl_443 ok critical "443 /api/health returned 200" "{\"http_code\": 200}"
  else
    add_check takctl_443 fail critical "443 /api/health http_code=$code" "{\"http_code\": \"${code:-000}\"}"
  fi
}

check_8446_tls() {
  local fqdn="$1"
  if [ -z "$fqdn" ]; then
    add_check tak_8446_tls warn critical "fqdn missing"
    return
  fi
  if ! port_tcp_listening 8446; then
    add_check tak_8446_tls fail critical "8446 not listening"
    return
  fi
  local code
  code="$(http_code_insecure "https://$fqdn:8446/" --resolve "$fqdn:8446:127.0.0.1")"
  case "$code" in
    200|301|302|401|403|404)
      add_check tak_8446_tls ok critical "8446 TLS reachable http_code=$code" "{\"http_code\": $code}"
      ;;
    *)
      add_check tak_8446_tls fail critical "8446 TLS failed http_code=$code" "{\"http_code\": \"${code:-000}\"}"
      ;;
  esac
}

check_8443_mtls() {
  local fqdn="$1"
  if [ -z "$fqdn" ]; then
    add_check tak_8443_mtls warn warn "fqdn missing"
    return
  fi
  if ! port_tcp_listening 8443; then
    add_check tak_8443_mtls fail critical "8443 not listening"
    return
  fi
  if ! have_admin_identity; then
    add_check tak_8443_mtls warn warn "8443 listening, but admin identity missing; mTLS probe skipped"
    return
  fi

  local pem key ca keypass result ok msg
  pem="$(admin_pem)"
  key="$(admin_key)"
  ca="$(admin_ca)"
  keypass="$(client_key_passphrase || true)"

  result="$(python3 - <<'PY2' "$fqdn" "$pem" "$key" "$ca" "$keypass"
import json
import socket
import ssl
import sys

fqdn, pem, key, ca, keypass = sys.argv[1:6]
try:
    ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=ca)
    ctx.check_hostname = True
    ctx.load_cert_chain(certfile=pem, keyfile=key, password=(keypass or None))
    with socket.create_connection(("127.0.0.1", 8443), timeout=8) as raw:
        with ctx.wrap_socket(raw, server_hostname=fqdn) as tls:
            req = (
                f"HEAD /Marti/api/server/version HTTP/1.1\r\n"
                f"Host: {fqdn}:8443\r\n"
                f"Connection: close\r\n\r\n"
            ).encode("utf-8")
            tls.settimeout(8)
            tls.sendall(req)
            data = b""
            while b"\r\n" not in data:
                chunk = tls.recv(4096)
                if not chunk:
                    break
                data += chunk
    line = data.split(b"\r\n", 1)[0].decode("utf-8", "replace").strip()
    parts = line.split()
    code = int(parts[1]) if len(parts) >= 2 and parts[1].isdigit() else 0
    if code in (200, 401, 403, 404):
        print(json.dumps({"ok": True, "msg": f"8443 mTLS reachable http_code={code}"}))
    else:
        print(json.dumps({"ok": False, "msg": f"8443 mTLS failed http_code={code or '000'}"}))
except Exception as e:
    print(json.dumps({"ok": False, "msg": f"{type(e).__name__}: {e}"}))
PY2
)"

  ok="$(python3 - <<'PY2' "$result"
import json, sys
d = json.loads(sys.argv[1]); print("1" if d.get("ok") else "0")
PY2
)"
  msg="$(python3 - <<'PY2' "$result"
import json, sys
d = json.loads(sys.argv[1]); print(d.get("msg", ""))
PY2
)"

  if [ "$ok" = "1" ]; then
    add_check tak_8443_mtls ok warn "$msg"
  else
    add_check tak_8443_mtls fail warn "$msg"
  fi
}

check_8089_cot_mtls() {
  local fqdn="$1"
  if [ -z "$fqdn" ]; then
    add_check cot_8089_mtls warn warn "fqdn missing"
    return
  fi
  if ! port_tcp_listening 8089; then
    add_check cot_8089_mtls fail critical "8089 not listening"
    return
  fi
  if ! have_admin_identity; then
    add_check cot_8089_mtls warn warn "admin identity missing for CoT mTLS probe"
    return
  fi

  local pem key ca keypass result ok msg
  pem="$(admin_pem)"
  key="$(admin_key)"
  ca="$(admin_ca)"
  keypass="$(client_key_passphrase || true)"

  if [ -z "$keypass" ]; then
    add_check cot_8089_mtls warn warn "8089 listening, but no client key passphrase found in secrets.d; CoT mTLS probe skipped"
    return
  fi

  result="$(python3 - <<'PY2' "$fqdn" "$pem" "$key" "$ca" "$keypass"
import json
import socket
import ssl
import sys
import time

fqdn, pem, key, ca, keypass = sys.argv[1:6]
uid = f"health-{socket.gethostname()}-{int(time.time())}"
now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
payload = f'<event version="2.0" uid="{uid}" type="t-x-c-t" time="{now}" start="{now}" stale="{now}" how="h-g-i-g-o"/>'.encode("utf-8")

try:
    ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=ca)
    ctx.check_hostname = True
    ctx.load_cert_chain(certfile=pem, keyfile=key, password=keypass)
    with socket.create_connection(("127.0.0.1", 8089), timeout=8) as raw:
        with ctx.wrap_socket(raw, server_hostname=fqdn) as tls:
            tls.settimeout(8)
            tls.sendall(payload)
            try:
                tls.shutdown(socket.SHUT_WR)
            except Exception:
                pass
    print(json.dumps({"ok": True, "msg": "8089 mTLS connect + CoT write OK"}))
except Exception as e:
    print(json.dumps({"ok": False, "msg": f"{type(e).__name__}: {e}"}))
PY2
)"

  ok="$(python3 - <<'PY2' "$result"
import json, sys
d = json.loads(sys.argv[1]); print("1" if d.get("ok") else "0")
PY2
)"
  msg="$(python3 - <<'PY2' "$result"
import json, sys
d = json.loads(sys.argv[1]); print(d.get("msg", ""))
PY2
)"

  if [ "$ok" = "1" ]; then
    add_check cot_8089_mtls ok warn "$msg"
  else
    add_check cot_8089_mtls fail warn "$msg"
  fi
}

check_martine() {
  local st recent raw_age martine_age

  st="$(service_state martine-cot.service)"
  recent="$(journalctl -u martine-cot.service --since '-10 min' --no-pager 2>/dev/null | tail -n 200 | grep -E 'cot_tls_client.*error=|PEM lib|SSLError|Traceback' | tail -n 1 || true)"

  raw_age="$(sudo -u postgres psql -d cot -Atqc "SELECT COALESCE(EXTRACT(EPOCH FROM (NOW() - MAX(servertime))), 999999999)::bigint FROM cot_router WHERE uid = 'ANDROID-MARTINE';" 2>/dev/null || true)"
  martine_age="$(printf '%s' "$raw_age" | tr -cd '0-9')"
  [ -n "$martine_age" ] || martine_age="999999999"

  case "$st" in
    active)
      if [ -n "$recent" ]; then
        add_check martine_service fail warn "martine-cot.service active but recent CoT/TLS error seen in journal"
      else
        add_check martine_service ok info "martine-cot.service active"
      fi
      ;;
    *)
      add_check martine_service fail warn "martine-cot.service state=$st"
      ;;
  esac

  if [ "$martine_age" -le 90 ]; then
    add_check martine_presence ok info "ANDROID-MARTINE seen in cot_router ${martine_age}s ago"
  elif [ "$martine_age" -le 300 ]; then
    add_check martine_presence warn warn "ANDROID-MARTINE presence stale in cot_router (${martine_age}s ago)"
  elif [ "$martine_age" -lt 999999999 ]; then
    add_check martine_presence fail warn "ANDROID-MARTINE not fresh in cot_router (${martine_age}s ago)"
  else
    add_check martine_presence fail warn "ANDROID-MARTINE not found in cot_router"
  fi
}

check_mumble() {
  local st
  st="$(service_state mumble-server.service)"
  if [ "$st" = "active" ] && { port_tcp_listening 64738 || port_udp_listening 64738; }; then
    add_check mumble ok warn "mumble-server active and listening on 64738"
  elif [ "$st" = "active" ]; then
    add_check mumble warn warn "mumble-server active but 64738 not detected"
  else
    add_check mumble warn warn "mumble-server.service state=$st"
  fi
}

check_nginx_upstream_8080_errors() {
  local result count
  result="$(python3 - <<'PY2'
from pathlib import Path
import json

p = Path("/var/log/nginx/error.log")
count = 0
samples = []

if p.exists():
    try:
        lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        lines = []
    for line in lines[-5000:]:
        ll = line.lower()
        if "127.0.0.1:8080" in line and "upstream" in ll:
            count += 1
            if len(samples) < 3:
                samples.append(line[:220])

print(json.dumps({"count": count, "samples": samples}))
PY2
)"
  count="$(python3 - <<'PY2' "$result"
import json, sys
d = json.loads(sys.argv[1]); print(int(d.get("count", 0)))
PY2
)"
  if [ "$count" -eq 0 ]; then
    add_check nginx_upstream_8080 ok warn "no recent nginx upstream errors to 127.0.0.1:8080" "$result"
  else
    add_check nginx_upstream_8080 warn warn "recent nginx upstream errors to 127.0.0.1:8080: $count" "$result"
  fi
}

check_cert_expiry() {
  local fqdn="$1"
  local cert="/etc/letsencrypt/live/$fqdn/fullchain.pem"
  if [ -z "$fqdn" ] || [ ! -f "$cert" ]; then
    add_check cert_expiry warn warn "LE cert missing"
    return
  fi
  local days
  days="$(python3 - <<'PY2' "$cert"
from datetime import datetime, timezone
from pathlib import Path
import subprocess, sys

cert = Path(sys.argv[1])
try:
    out = subprocess.check_output(["openssl", "x509", "-noout", "-enddate", "-in", str(cert)], text=True).strip()
    _, val = out.split("=", 1)
    dt = datetime.strptime(val, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
    days = int((dt - datetime.now(timezone.utc)).total_seconds() // 86400)
    print(days)
except Exception:
    print("")
PY2
)"
  if [ -z "$days" ]; then
    add_check cert_expiry warn warn "cert expiry unreadable"
  elif [ "$days" -lt 7 ]; then
    add_check cert_expiry fail warn "LE cert expires in $days days" "{\"days_left\": $days}"
  elif [ "$days" -lt 21 ]; then
    add_check cert_expiry warn warn "LE cert expires in $days days" "{\"days_left\": $days}"
  else
    add_check cert_expiry ok warn "LE cert expires in $days days" "{\"days_left\": $days}"
  fi
}

detect_bedrock_provider() {
  python3 - <<'PY2'
from pathlib import Path
for base in [Path("/opt/tak/tools/takctl/conf.d"), Path("/opt/tak/tools/takctl")]:
    files = sorted(base.glob("*.conf")) if base.is_dir() else ([base] if base.is_file() else [])
    for p in files:
        for raw in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = [x.strip() for x in line.split("=", 1)]
            if "provider" in k.lower() and v.lower() in {"bedrock", "local"}:
                print(v.lower())
                raise SystemExit
print("")
PY2
}

detect_bedrock_model() {
  python3 - <<'PY2'
from pathlib import Path
cands = []
for base in [Path("/opt/tak/tools/takctl/conf.d"), Path("/opt/tak/tools/takctl")]:
    files = sorted(base.glob("*.conf")) if base.is_dir() else ([base] if base.is_file() else [])
    for p in files:
        for raw in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = [x.strip() for x in line.split("=", 1)]
            kl = k.lower()
            vl = v.lower()
            if "model" in kl and any(x in vl for x in ["anthropic", "claude", "amazon.", "eu."]):
                cands.append(v)
print(cands[0] if cands else "")
PY2
}

bedrock_probe_json() {
  local provider model py
  provider="$(detect_bedrock_provider)"
  model="$(detect_bedrock_model)"
  py="/opt/tak/tools/martine/.venv/bin/python"

  if [ "$provider" != "bedrock" ]; then
    python3 - <<'PY2'
import json
print(json.dumps({
    "auth_ok": None,
    "auth_msg": "provider is not bedrock",
    "inference_ok": None,
    "inference_msg": "provider is not bedrock",
    "auth_mode": None,
    "model": None,
}))
PY2
    return 0
  fi

  if [ ! -x "$py" ]; then
    python3 - <<'PY2'
import json
print(json.dumps({
    "auth_ok": False,
    "auth_msg": "martine venv python missing for boto3 check",
    "inference_ok": False,
    "inference_msg": "martine venv python missing for boto3 check",
    "auth_mode": None,
    "model": None,
}))
PY2
    return 0
  fi

  "$py" - <<'PY2' "$BEDROCK_CACHE" "$model"
from pathlib import Path
from datetime import datetime, timezone, timedelta
import json
import os
import sys

cache = Path(sys.argv[1])
model = sys.argv[2].strip()
now = datetime.now(timezone.utc)

def _strip_quotes(v: str) -> str:
    v = (v or "").strip()
    if len(v) >= 2 and ((v[0] == '"' and v[-1] == '"') or (v[0] == "'" and v[-1] == "'")):
        v = v[1:-1]
    return v.strip()

def load_bedrock_api_key() -> str:
    bases = [
        Path("/opt/tak/tools/takctl/secrets.d"),
        Path("/etc/taks-bootstrap.d/secrets.d"),
        Path("/opt/tak/tools/takctl"),
    ]
    for base in bases:
        files = sorted(base.glob("*.conf")) if base.is_dir() else ([base] if base.is_file() and base.suffix == ".conf" else [])
        for p in files:
            try:
                lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
            except Exception:
                continue
            for raw in lines:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = [x.strip() for x in line.split("=", 1)]
                if k == "bedrock_api_key":
                    return _strip_quotes(v)
    return ""

api_key = load_bedrock_api_key()
auth_mode = "api_key" if api_key else "aws_credentials"

if api_key:
    os.environ["AWS_BEARER_TOKEN_BEDROCK"] = api_key

if cache.exists():
    try:
        data = json.loads(cache.read_text(encoding="utf-8"))
        ts = datetime.fromisoformat(data["updated_at"].replace("Z", "+00:00"))
        cache_mode = str(data.get("auth_mode") or "")
        cache_auth_ok = data.get("auth_ok")
        if (
            now - ts < timedelta(hours=1)
            and cache_mode == auth_mode
            and cache_auth_ok is True
        ):
            print(json.dumps(data))
            raise SystemExit
    except SystemExit:
        raise
    except Exception:
        pass

try:
    from botocore.config import Config
    import boto3

    cfg = Config(connect_timeout=4, read_timeout=8, retries={"max_attempts": 1})

    bedrock = boto3.client("bedrock", region_name="eu-north-1", config=cfg)
    bedrock.list_foundation_models()

    auth_ok = True
    auth_msg = "bedrock auth/list OK via api_key" if api_key else "bedrock auth/list OK"

    if model:
        rt = boto3.client("bedrock-runtime", region_name="eu-north-1", config=cfg)
        try:
            rt.converse(
                modelId=model,
                messages=[{"role": "user", "content": [{"text": "ping"}]}],
                inferenceConfig={"maxTokens": 1, "temperature": 0.0},
            )
            inf_ok = True
            inf_msg = f"minimal converse OK for {model}"
        except Exception as e:
            inf_ok = False
            inf_msg = f"minimal converse failed for {model}: {type(e).__name__}: {e}"
    else:
        inf_ok = None
        inf_msg = "bedrock model unresolved from config"

    payload = {
        "updated_at": now.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "auth_ok": auth_ok,
        "auth_msg": auth_msg,
        "inference_ok": inf_ok,
        "inference_msg": inf_msg,
        "model": model or None,
        "auth_mode": "api_key" if api_key else "aws_credentials",
    }
except Exception as e:
    payload = {
        "updated_at": now.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "auth_ok": False,
        "auth_msg": f"{type(e).__name__}: {e}",
        "inference_ok": False if model else None,
        "inference_msg": "auth failed; inference skipped" if model else "bedrock model unresolved from config",
        "model": model or None,
        "auth_mode": "api_key" if api_key else "aws_credentials",
    }

cache.parent.mkdir(parents=True, exist_ok=True)
cache.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
print(json.dumps(payload))
PY2
}

check_bedrock_auth() {
  local result auth_ok auth_msg
  result="$(bedrock_probe_json)"
  auth_ok="$(python3 - <<'PY2' "$result"
import json, sys
d = json.loads(sys.argv[1]); v = d.get("auth_ok"); print("null" if v is None else ("1" if v else "0"))
PY2
)"
  auth_msg="$(python3 - <<'PY2' "$result"
import json, sys
d = json.loads(sys.argv[1]); print(d.get("auth_msg", ""))
PY2
)"
  case "$auth_ok" in
    1) add_check bedrock_auth ok warn "$auth_msg" ;;
    0) add_check bedrock_auth warn warn "$auth_msg" ;;
    *) add_check bedrock_auth skip warn "$auth_msg" ;;
  esac
}

check_bedrock_inference() {
  local result inf_ok inf_msg
  result="$(bedrock_probe_json)"
  inf_ok="$(python3 - <<'PY2' "$result"
import json, sys
d = json.loads(sys.argv[1]); v = d.get("inference_ok"); print("null" if v is None else ("1" if v else "0"))
PY2
)"
  inf_msg="$(python3 - <<'PY2' "$result"
import json, sys
d = json.loads(sys.argv[1]); print(d.get("inference_msg", ""))
PY2
)"
  case "$inf_ok" in
    1) add_check bedrock_inference ok warn "$inf_msg" ;;
    0) add_check bedrock_inference warn warn "$inf_msg" ;;
    *) add_check bedrock_inference skip warn "$inf_msg" ;;
  esac
}

check_weather() {
  local st
  st="$(service_state takctl-weather-refresh.timer)"
  case "$st" in
    active) add_check weather_service ok warn "takctl-weather-refresh.timer active" ;;
    *) add_check weather_service skip warn "weather upstream not probed yet; timer state=$st" ;;
  esac
}

write_json() {
  mkdir -p "$OUT_DIR"
  TMP_JSON="$(mktemp)"
  python3 - <<'PY2' "$CHECKS_TSV" "$TMP_JSON"
import json, sys
from datetime import datetime, timezone

rows = []
with open(sys.argv[1], "r", encoding="utf-8") as f:
    for raw in f:
        raw = raw.rstrip("\n")
        if not raw:
            continue
        name, status, severity, summary, extra = raw.split("\t", 4)
        try:
            extra_obj = json.loads(extra)
        except Exception:
            extra_obj = {}
        item = {"status": status, "severity": severity, "summary": summary}
        if isinstance(extra_obj, dict):
            item.update(extra_obj)
        rows.append((name, item))

checks = {k: v for k, v in rows}
critical_failed = sum(1 for _, v in rows if v["severity"] == "critical" and v["status"] == "fail")
warn_failed = sum(1 for _, v in rows if v["severity"] != "critical" and v["status"] in {"fail", "warn"})
total_checks = len(rows)
ok_count = sum(1 for _, v in rows if v["status"] == "ok")
warn_count = sum(1 for _, v in rows if v["status"] == "warn")
fail_count = sum(1 for _, v in rows if v["status"] == "fail")
skip_count = sum(1 for _, v in rows if v["status"] == "skip")

overall = "ok"
if critical_failed:
    overall = "fail"
elif warn_failed:
    overall = "warn"

doc = {
    "version": 1,
    "updated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    "fresh_for_sec": 5400,
    "rollup": {
        "overall": overall,
        "critical_failed": critical_failed,
        "warn_failed": warn_failed,
        "total_checks": total_checks,
        "ok": ok_count,
        "warn": warn_count,
        "fail": fail_count,
        "skip": skip_count,
        "stale": False,
    },
    "checks": checks,
}

with open(sys.argv[2], "w", encoding="utf-8") as f:
    json.dump(doc, f, indent=2, ensure_ascii=False)
    f.write("\n")
PY2
  install -m 0644 "$TMP_JSON" "$OUT_JSON"
  log "wrote $OUT_JSON"
}
