#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUNDLE_ROOT="$ROOT"

INSTALL_DST="/opt/taks/install/taks-node-health.sh"
SERVICE_DST="/etc/systemd/system/taks-node-health.service"
TIMER_DST="/etc/systemd/system/taks-node-health.timer"

OUT_DIR="/opt/tak/takctl-state"
OUT_JSON="$OUT_DIR/node-health.json"
BEDROCK_CACHE="$OUT_DIR/node-health-bedrock.json"

NODE_CONF="/etc/taks-bootstrap.d/config.d/node.conf"
CHECKS_TSV=""
TMP_JSON=""

cleanup() {
  [ -n "${CHECKS_TSV:-}" ] && rm -f "$CHECKS_TSV" || true
  [ -n "${TMP_JSON:-}" ] && rm -f "$TMP_JSON" || true
}
trap cleanup EXIT

log() {
  printf '[taks-node-health] %s\n' "$*"
}

read_simple_kv() {
  local path="$1"
  local key="$2"
  [ -f "$path" ] || return 1
  sed -n "s/^[[:space:]]*${key}[[:space:]]*=[[:space:]]*//p" "$path" | head -n 1 | sed -e 's/[[:space:]]*$//'
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

service_enabled() {
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

admin_key_usable_without_passphrase() {
  local key
  key="$(admin_key)"
  [ -n "$key" ] || return 1
  openssl pkey -in "$key" -noout -passin pass: >/dev/null 2>&1
}

check_takserver_service() {
  local st
  st="$(service_state takserver.service)"
  if [ "$st" = "active" ]; then
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
  st="$(service_enabled takctl-web.service)"
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
  code="$(http_code "https://$fqdn/takctl/api/health" --resolve "$fqdn:443:127.0.0.1")"
  if [ "$code" = "200" ]; then
    add_check takctl_443 ok critical "443 /takctl/api/health returned 200" "{\"http_code\": 200}"
  else
    add_check takctl_443 fail critical "443 /takctl/api/health http_code=$code" "{\"http_code\": \"${code:-000}\"}"
  fi
}

check_8446_tls() {
  local fqdn="$1"
  if [ -z "$fqdn" ]; then
    add_check tak_8446_tls warn critical "fqdn missing"
    return
  fi
  local code
  code="$(http_code "https://$fqdn:8446/" --resolve "$fqdn:8446:127.0.0.1")"
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

  if ! have_admin_identity; then
    if port_tcp_listening 8443; then
      add_check tak_8443_mtls warn warn "8443 listening, but admin identity missing for mTLS probe"
    else
      add_check tak_8443_mtls fail critical "8443 not listening and admin identity missing for mTLS probe"
    fi
    return
  fi

  if ! admin_key_usable_without_passphrase; then
    if port_tcp_listening 8443; then
      add_check tak_8443_mtls warn warn "8443 listening, but admin key is passphrase-protected; mTLS probe skipped"
    else
      add_check tak_8443_mtls fail critical "8443 not listening and admin key is passphrase-protected; mTLS probe skipped"
    fi
    return
  fi

  local pem key ca code
  pem="$(admin_pem)"
  key="$(admin_key)"
  ca="$(admin_ca)"
  code="$(http_code "https://$fqdn:8443/Marti/api/server/version" \
    --resolve "$fqdn:8443:127.0.0.1" \
    --cert "$pem" --key "$key" --cacert "$ca")"
  case "$code" in
    200|401|403|404)
      add_check tak_8443_mtls ok critical "8443 mTLS reachable http_code=$code" "{\"http_code\": $code}"
      ;;
    *)
      add_check tak_8443_mtls fail critical "8443 mTLS failed http_code=$code" "{\"http_code\": \"${code:-000}\"}"
      ;;
  esac
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
print("1" if json.loads(sys.argv[1]).get("ok") else "0")
PY2
)"
  msg="$(python3 - <<'PY2' "$result"
import json, sys
print(json.loads(sys.argv[1]).get("msg", ""))
PY2
)"

  if [ "$ok" = "1" ]; then
    add_check cot_8089_mtls ok warn "$msg"
  else
    add_check cot_8089_mtls fail warn "$msg"
  fi
}

check_martine() {
  local st
  st="$(service_state martine-cot.service)"
  case "$st" in
    active) add_check martine_service ok warn "martine-cot.service active" ;;
    *) add_check martine_service warn warn "martine-cot.service state=$st" ;;
  esac
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
  result="$(python3 - <<'PY'
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json

path = Path("/var/log/nginx/error.log")
now = datetime.now(timezone.utc)
cutoff = now - timedelta(hours=6)
count = 0
samples = []

if path.is_file():
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if "connect() failed" not in line:
            continue
        if "127.0.0.1:8080" not in line:
            continue
        try:
            ts = datetime.strptime(line[:19], "%Y/%m/%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except Exception:
            continue
        if ts < cutoff:
            continue
        count += 1
        if len(samples) < 3:
            samples.append(line)

print(json.dumps({
    "count_last_6h": count,
    "samples": samples,
}, ensure_ascii=False))
PY
)"
  count="$(python3 - <<'PY' "$result"
import json, sys
d = json.loads(sys.argv[1])
print(int(d.get("count_last_6h", 0)))
PY
)"
  if [ "$count" -eq 0 ]; then
    add_check nginx_upstream_8080 ok warn "no recent nginx upstream errors to 127.0.0.1:8080" "$result"
  else
    add_check nginx_upstream_8080 warn warn "recent nginx upstream errors to 127.0.0.1:8080 in last 6h: $count" "$result"
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
  days="$(python3 - <<'PY' "$cert"
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
PY
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
  python3 - <<'PY'
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
PY
}

detect_bedrock_model() {
  python3 - <<'PY'
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
PY
}

check_bedrock() {
  local provider model py result
  provider="$(detect_bedrock_provider)"
  if [ "$provider" != "bedrock" ]; then
    add_check bedrock_auth skip warn "provider is not bedrock"
    add_check bedrock_inference skip warn "provider is not bedrock"
    return
  fi

  py="/opt/tak/tools/martine/.venv/bin/python"
  if [ ! -x "$py" ]; then
    add_check bedrock_auth warn warn "martine venv python missing for boto3 check"
    add_check bedrock_inference warn warn "martine venv python missing for boto3 check"
    return
  fi

  model="$(detect_bedrock_model)"
  result="$("$py" - <<'PY' "$BEDROCK_CACHE" "$model"
from pathlib import Path
from datetime import datetime, timezone, timedelta
import json, sys
cache = Path(sys.argv[1])
model = sys.argv[2].strip()
now = datetime.now(timezone.utc)
if cache.exists():
    try:
        data = json.loads(cache.read_text(encoding="utf-8"))
        ts = datetime.fromisoformat(data["updated_at"].replace("Z", "+00:00"))
        if now - ts < timedelta(hours=1):
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
    auth_msg = "bedrock auth/list OK"
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
    }
except Exception as e:
    payload = {
        "updated_at": now.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "auth_ok": False,
        "auth_msg": f"{type(e).__name__}: {e}",
        "inference_ok": False if model else None,
        "inference_msg": "auth failed; inference skipped" if model else "bedrock model unresolved from config",
        "model": model or None,
    }
cache.parent.mkdir(parents=True, exist_ok=True)
cache.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
print(json.dumps(payload))
PY
)"
  local auth_ok auth_msg inf_ok inf_msg
  auth_ok="$(python3 - <<'PY' "$result"
import json, sys
d = json.loads(sys.argv[1]); print("1" if d.get("auth_ok") else "0")
PY
)"
  auth_msg="$(python3 - <<'PY' "$result"
import json, sys
d = json.loads(sys.argv[1]); print(d.get("auth_msg", ""))
PY
)"
  inf_ok="$(python3 - <<'PY' "$result"
import json, sys
d = json.loads(sys.argv[1]); v = d.get("inference_ok"); print("null" if v is None else ("1" if v else "0"))
PY
)"
  inf_msg="$(python3 - <<'PY' "$result"
import json, sys
d = json.loads(sys.argv[1]); print(d.get("inference_msg", ""))
PY
)"
  if [ "$auth_ok" = "1" ]; then
    add_check bedrock_auth ok warn "$auth_msg"
  else
    add_check bedrock_auth warn warn "$auth_msg"
  fi
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
  python3 - <<'PY' "$CHECKS_TSV" "$TMP_JSON"
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
status_counts = {
    "ok": sum(1 for _, v in rows if v["status"] == "ok"),
    "warn": sum(1 for _, v in rows if v["status"] == "warn"),
    "fail": sum(1 for _, v in rows if v["status"] == "fail"),
    "skip": sum(1 for _, v in rows if v["status"] == "skip"),
}
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
        "total_checks": len(rows),
        "ok": status_counts["ok"],
        "warn": status_counts["warn"],
        "fail": status_counts["fail"],
        "skip": status_counts["skip"],
        "stale": False,
    },
    "checks": checks,
}

with open(sys.argv[2], "w", encoding="utf-8") as f:
    json.dump(doc, f, indent=2, ensure_ascii=False)
    f.write("\n")
PY
  install -m 0644 "$TMP_JSON" "$OUT_JSON"
  log "wrote $OUT_JSON"
}

run_probe() {
  CHECKS_TSV="$(mktemp)"
  local fqdn
  fqdn="$(get_fqdn)"
  check_takserver_service
  check_postgres
  check_disk_root
  check_80
  check_takctl_enabled
  check_takctl_active
  check_takctl_8080_local
  check_443_health "$fqdn"
  check_8446_tls "$fqdn"
  check_8443_mtls "$fqdn"
  check_8089_cot_mtls "$fqdn"
  check_martine
  check_mumble
  check_nginx_upstream_8080_errors
  check_cert_expiry "$fqdn"
  check_bedrock
  check_weather
  write_json
}

install_units() {
  install -d -m 0755 /opt/taks/install
  install -m 0755 "$BUNDLE_ROOT/install/taks-node-health.sh" "$INSTALL_DST"
  install -m 0644 "$BUNDLE_ROOT/install/systemd/taks-node-health.service" "$SERVICE_DST"
  install -m 0644 "$BUNDLE_ROOT/install/systemd/taks-node-health.timer" "$TIMER_DST"
  systemctl daemon-reload
  systemctl enable --now taks-node-health.timer
  systemctl start taks-node-health.service || true
  log "installed taks-node-health service+timer"
}

case "${1:-}" in
  --run)
    run_probe || {
      log "probe failed unexpectedly; writing degraded json"
      CHECKS_TSV="$(mktemp)"
      add_check node_health fail critical "node health collector crashed"
      write_json || true
    }
    ;;
  *)
    install_units
    ;;
esac
