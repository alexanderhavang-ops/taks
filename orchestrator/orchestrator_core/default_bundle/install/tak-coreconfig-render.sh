#!/usr/bin/env bash
set -euo pipefail

log() {
  printf '[tak-coreconfig-render] %s\n' "$*"
}

die() {
  printf '[tak-coreconfig-render] ERROR: %s\n' "$*" >&2
  exit 1
}

require_root() {
  [ "$(id -u)" -eq 0 ] || die "must run as root"
}

read_trimmed_file_optional() {
  local p="$1"
  [ -f "$p" ] || return 1
  tr -d '\r' < "$p" | sed -e 's/[[:space:]]*$//' | head -n 1
}

read_simple_kv() {
  local path="$1"
  local key="$2"
  [ -f "$path" ] || die "required file missing: $path"
  sed -n "s/^[[:space:]]*${key}[[:space:]]*=[[:space:]]*//p" "$path" | head -n 1 | sed -e 's/[[:space:]]*$//'
}

read_shell_assignment() {
  local p="$1"
  local key="$2"
  [ -f "$p" ] || die "required file missing: $p"
  local v
  v="$(sed -n "s/^${key}=//p" "$p" | head -n 1)"
  [ -n "$v" ] || die "missing shell assignment ${key} in $p"
  case "$v" in
    \"*\") v="${v#\"}"; v="${v%\"}" ;;
    \'*\') v="${v#\'}"; v="${v%\'}" ;;
  esac
  printf '%s\n' "$v"
}

require_boot_fqdn() {
  local boot_conf="/etc/taks-bootstrap.d/config.d/node.conf"
  local fqdn=""
  fqdn="$(read_simple_kv "$boot_conf" node_fqdn || true)"
  if [ -z "$fqdn" ]; then
    fqdn="$(read_simple_kv "$boot_conf" fqdn || true)"
  fi
  [ -n "$fqdn" ] || die "missing node_fqdn/fqdn in $boot_conf"
  printf '%s\n' "$fqdn"
}

xml_escape() {
  sed \
    -e 's/&/\&amp;/g' \
    -e 's/"/\&quot;/g' \
    -e "s/'/\&apos;/g" \
    -e 's/</\&lt;/g' \
    -e 's/>/\&gt;/g'
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

read_simple_kv_optional() {
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
    v="$(read_simple_kv_optional "$f" "$key" || true)"
    if [ -n "${v:-}" ]; then
      strip_wrapping_quotes "$v"
      return 0
    fi
  done
  return 1
}

cfg_value() {
  local key="$1"
  local default="${2:-}"
  local v=""
  v="$(read_kv_first_hit_in_dir /opt/tak/tools/takctl/conf.d "$key" || true)"
  [ -n "$v" ] || v="$(read_simple_kv_optional /etc/taks/ldap.conf "$key" 2>/dev/null | sed -e 's/[[:space:]]*$//' || true)"
  [ -n "$v" ] || v="$(read_kv_first_hit_in_dir /etc/taks-bootstrap.d/config.d "$key" || true)"
  [ -n "$v" ] || v="$default"
  strip_wrapping_quotes "$v"
}

secret_value() {
  local key="$1"
  local default="${2:-}"
  local v=""
  v="$(read_kv_first_hit_in_dir /opt/tak/tools/takctl/secrets.d "$key" || true)"
  [ -n "$v" ] || v="$(read_simple_kv_optional /etc/taks/ldap-secrets.conf "$key" 2>/dev/null | sed -e 's/[[:space:]]*$//' || true)"
  [ -n "$v" ] || v="$(read_kv_first_hit_in_dir /etc/taks-bootstrap.d/secrets.d "$key" || true)"
  [ -n "$v" ] || v="$default"
  strip_wrapping_quotes "$v"
}

xml_attr() {
  printf '%s' "${1:-}" | xml_escape
}

render_auth_block() {
  local store
  store="$(cfg_value backing_user_store userauthfile | tr '[:upper:]' '[:lower:]')"

  case "$store" in
    ldap|ldap_local|openldap)
      local uri base people groups services service_dn service_pw user_string update_interval
      local people_base tak_ldap_url tak_userstring
      local group_object_class group_name_attr group_member_attr group_regex
      uri="$(cfg_value ldap_uri ldap://127.0.0.1:389)"
      base="$(cfg_value ldap_base_dn dc=taks,dc=local)"
      people="$(cfg_value ldap_people_ou people)"
      groups="$(cfg_value ldap_groups_ou groups)"
      services="$(cfg_value ldap_services_ou services)"
      service_dn="$(cfg_value ldap_service_account_dn "cn=taksvc,ou=${services},${base}")"
      service_pw="$(secret_value ldap_service_account_password '')"
      user_string="$(cfg_value ldap_user_string "uid={username},ou=${people},${base}")"
      people_base="ou=${people},${base}"

      # TAKServer CoreConfig expects:
      #   url        = LDAP URL including the user search/base DN
      #   userstring = login/RDN pattern relative to that URL, usually uid={username}
      #
      # takctl's LDAP writer still uses ldap_user_string as a full user DN pattern.
      # So derive TAKServer's auth view from the same config unless explicitly
      # overridden for a shared/external LDAP directory.
      tak_ldap_url="$(cfg_value ldap_auth_url '')"
      if [ -z "$tak_ldap_url" ]; then
        tak_ldap_url="${uri%/}/${people_base}"
      fi

      tak_userstring="$(cfg_value ldap_auth_userstring '')"
      if [ -z "$tak_userstring" ]; then
        case "$user_string" in
          *,${people_base}) tak_userstring="${user_string%,${people_base}}" ;;
          *) tak_userstring="uid={username}" ;;
        esac
      fi

      update_interval="$(cfg_value ldap_update_interval_sec 60)"
      group_object_class="$(cfg_value ldap_group_object_class groupOfNames)"
      group_name_attr="$(cfg_value ldap_group_name_attr cn)"
      group_member_attr="$(cfg_value ldap_group_member_attr member)"
      group_regex="$(cfg_value ldap_group_name_extractor_regex '^cn=([^,]+),.*$')"

      [ -n "$service_pw" ] || die "backing_user_store=ldap but ldap_service_account_password is missing"

      cat <<EOF_AUTH
    <auth x509useGroupCache="true">
        <ldap
            url="$(xml_attr "$tak_ldap_url")"
            userstring="$(xml_attr "$tak_userstring")"
            updateInterval="$(xml_attr "$update_interval")"
            groupBaseRDN="$(xml_attr "ou=${groups},${base}")"
            groupObjectClass="$(xml_attr "$group_object_class")"
            groupNameAttribute="$(xml_attr "$group_name_attr")"
            groupMemberAttribute="$(xml_attr "$group_member_attr")"
            groupNameExtractorRegex="$(xml_attr "$group_regex")"
            serviceAccountDN="$(xml_attr "$service_dn")"
            serviceAccountCredential="$(xml_attr "$service_pw")"/>
    </auth>
EOF_AUTH
      ;;
    userauthfile|file|xml|marti_xml|'')
      cat <<'EOF_AUTH'
    <auth x509useGroupCache="true">
        <File location="UserAuthenticationFile.xml"/>
    </auth>
EOF_AUTH
      ;;
    *)
      die "unknown backing_user_store=$store"
      ;;
  esac
}

extract_db_password() {
  local cfg="/opt/tak/CoreConfig.xml"
  [ -f "$cfg" ] || return 1
  python3 - "$cfg" <<'PYXML'
import re, sys
text = open(sys.argv[1], "r", encoding="utf-8").read()
m = re.search(r'<connection\b[^>]*\busername="martiuser"[^>]*\bpassword="([^"]+)"', text)
if m:
    print(m.group(1))
PYXML
}

generate_db_password() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 24
    return 0
  fi
  if command -v python3 >/dev/null 2>&1; then
    python3 - <<'PY'
import secrets
print(secrets.token_hex(24))
PY
    return 0
  fi
  if command -v uuidgen >/dev/null 2>&1; then
    printf '%s%s\n' "$(uuidgen | tr -d '-')" "$(uuidgen | tr -d '-')"
    return 0
  fi
  die "cannot generate db password (need openssl, python3, or uuidgen)"
}

sync_martiuser_password() {
  local pw="$1"
  command -v psql >/dev/null 2>&1 || die "psql missing"

  sudo -u postgres psql -d postgres -v ON_ERROR_STOP=1 --set=pw="$pw" >/dev/null <<'PSQL'
ALTER ROLE martiuser WITH PASSWORD :'pw';
PSQL
}

verify_coreconfig_keystores() {
  local cfg="/opt/tak/CoreConfig.xml"
  [ -f "$cfg" ] || die "missing CoreConfig.xml: $cfg"
  command -v keytool >/dev/null 2>&1 || die "keytool missing"
  command -v uuidgen >/dev/null 2>&1 || die "uuidgen missing"

  python3 - "$cfg" <<'PYXML' | while IFS=$'\t' read -r ctx role storetype path storepass alias keypass; do
import sys
import xml.etree.ElementTree as ET

cfg = sys.argv[1]
ns = {"m": "http://bbn.com/marti/xml/config"}
root = ET.parse(cfg).getroot()
items = []

def add(ctx, role, storetype, path, storepass, alias="", keypass=""):
    storetype = (storetype or "").strip() or "JKS"
    path = (path or "").strip()
    storepass = "" if storepass is None else str(storepass)
    alias = "" if alias is None else str(alias)
    keypass = "" if keypass is None else str(keypass)
    if path and storepass:
        items.append((ctx, role, storetype, path, storepass, alias, keypass))

for elem in root.findall(".//m:connector", ns):
    name = elem.attrib.get("_name", "")
    add(f"connector:{name}", "keystore",
        elem.attrib.get("keystore"),
        elem.attrib.get("keystoreFile"),
        elem.attrib.get("keystorePass"))

for elem in root.findall(".//m:jwt/m:keystore", ns):
    add("jwt", "keystore",
        elem.attrib.get("type"),
        elem.attrib.get("file"),
        elem.attrib.get("password"),
        elem.attrib.get("keyAlias"),
        elem.attrib.get("keyPassword"))

tls_i = 0
for elem in root.findall(".//m:tls", ns):
    tls_i += 1
    add(f"tls:{tls_i}:keystore", "keystore",
        elem.attrib.get("keystore"),
        elem.attrib.get("keystoreFile"),
        elem.attrib.get("keystorePass"),
        elem.attrib.get("keystoreKeyAlias"),
        elem.attrib.get("keystoreKeyPass"))
    add(f"tls:{tls_i}:truststore", "truststore",
        elem.attrib.get("truststore"),
        elem.attrib.get("truststoreFile"),
        elem.attrib.get("truststorePass"))

for elem in root.findall(".//m:TAKServerCAConfig", ns):
    add("TAKServerCAConfig", "keystore",
        elem.attrib.get("keystore"),
        elem.attrib.get("keystoreFile"),
        elem.attrib.get("keystorePass"),
        elem.attrib.get("keyAlias"),
        elem.attrib.get("keystorePass"))

seen = set()
for row in items:
    if row in seen:
        continue
    seen.add(row)
    print("\t".join(row))
PYXML
    [ -n "${ctx:-}" ] || continue

    local abs="$path"
    if [[ "$abs" != /* ]]; then
      abs="/opt/tak/$abs"
    fi

    [ -f "$abs" ] || die "CoreConfig store missing for $ctx: $abs"

    if ! keytool -list -storetype "$storetype" -keystore "$abs" -storepass "$storepass" >/dev/null 2>&1; then
      die "CoreConfig store/password mismatch for $ctx: $path (type=$storetype)"
    fi

    if [ "$role" = "keystore" ] && [ -n "$alias" ]; then
      if ! keytool -list -storetype "$storetype" -keystore "$abs" -storepass "$storepass" -alias "$alias" >/dev/null 2>&1; then
        die "CoreConfig alias missing/mismatch for $ctx: $path alias=$alias"
      fi
    fi

    if [ "$role" = "keystore" ] && [ -n "$alias" ] && [ -n "$keypass" ]; then
      tmpdir="$(mktemp -d /tmp/tak-keytest.XXXXXX)"
      tmpdst="$tmpdir/out.p12"
      tmppass="$(uuidgen | tr -d '-')"
      if ! keytool -importkeystore \
          -noprompt \
          -srckeystore "$abs" \
          -srcstoretype "$storetype" \
          -srcstorepass "$storepass" \
          -srcalias "$alias" \
          -srckeypass "$keypass" \
          -destkeystore "$tmpdst" \
          -deststoretype PKCS12 \
          -deststorepass "$tmppass" \
          -destkeypass "$tmppass" >/dev/null 2>&1; then
        rm -rf "$tmpdir"
        die "CoreConfig key alias/password mismatch for $ctx: $path alias=$alias"
      fi
      rm -rf "$tmpdir"
    fi

    log "verified $ctx -> $path"
  done
}

main() {
  require_root

  local taks_dir="/etc/taks"
  local cert_meta="/opt/tak/certs/cert-metadata.sh"
  local out="/opt/tak/CoreConfig.xml"
  local server_id_file="$taks_dir/server_id"

  local fqdn private_ip db_password cert_pass cert_capass org ou org_xml ou_xml
  local server_store_rel server_store_abs cert_https_store_rel cert_https_store_abs auth_xml

  fqdn="$(require_boot_fqdn)"

  private_ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
  [ -n "$private_ip" ] || die "unable to determine private IP"

  db_password="$(extract_db_password || true)"
  if [ -z "$db_password" ]; then
    db_password="$(generate_db_password)"
  fi
  [ -n "$db_password" ] || die "missing martiuser db password"

  cert_pass="$(read_shell_assignment "$cert_meta" PASS)"
  cert_capass="$(read_shell_assignment "$cert_meta" CAPASS)"
  org="$(read_shell_assignment "$cert_meta" ORGANIZATION)"
  ou="$(read_shell_assignment "$cert_meta" ORGANIZATIONAL_UNIT)"

  mkdir -p "$taks_dir"
  if [ ! -f "$server_id_file" ]; then
    uuidgen | tr -d '\r\n' > "$server_id_file"
  fi

  local server_id
  server_id="$(read_trimmed_file_optional "$server_id_file" || true)"
  [ -n "$server_id" ] || die "server_id missing in $server_id_file"

  org_xml="$(printf '%s' "$org" | xml_escape)"
  ou_xml="$(printf '%s' "$ou" | xml_escape)"

  server_store_rel="certs/files/02_SERVER/takserver-${fqdn}.p12"
  server_store_abs="/opt/tak/${server_store_rel}"
  [ -f "$server_store_abs" ] || die "missing server store: $server_store_abs"

  cert_https_store_rel="certs/files/03_PUBLIC/takserver-le-8446.p12"
  cert_https_store_abs="/opt/tak/${cert_https_store_rel}"
  [ -f "$cert_https_store_abs" ] || die "missing 8446 public LE store: $cert_https_store_abs"

  mkdir -p /opt/tak

  auth_xml="$(render_auth_block)"

  cat > "$out" <<EOF2
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Configuration xmlns="http://bbn.com/marti/xml/config">
    <network multicastTTL="5" serverId="${server_id}" version="5.6-RELEASE-6-HEAD">
        <input _name="stdssl" protocol="tls" port="8089" coreVersion="2" clientAuth="true"/>
        <input _name="quic" protocol="quic" port="8090"/>
        <input auth="anonymous" _name="replayudp" protocol="udp" port="6969"/>
        <connector port="8443" _name="https"/>
        <connector port="8444" useFederationTruststore="true" _name="fed_https"/>
        <connector port="8446" clientAuth="false" _name="cert_https" keystore="PKCS12" keystoreFile="${cert_https_store_rel}" keystorePass="${cert_pass}" enableWebtak="true"/>
        <announce/>
    </network>
${auth_xml}
    <submission ignoreStaleMessages="false" validateXml="false"/>
    <subscription reloadPersistent="false"/>
    <repository enable="true" numDbConnections="200" primaryKeyBatchSize="500" insertionBatchSize="500">
        <connection url="jdbc:postgresql://127.0.0.1:5432/cot" username="martiuser" password="${db_password}"/>
    </repository>
    <repeater enable="true" periodMillis="3000" staleDelayMillis="15000">
        <repeatableType initiate-test="/event/detail/emergency[@type='911 Alert']" cancel-test="/event/detail/emergency[@cancel='true']" _name="911"/>
        <repeatableType initiate-test="/event/detail/emergency[@type='Ring The Bell']" cancel-test="/event/detail/emergency[@cancel='true']" _name="RingTheBell"/>
        <repeatableType initiate-test="/event/detail/emergency[@type='Geo-fence Breached']" cancel-test="/event/detail/emergency[@cancel='true']" _name="GeoFenceBreach"/>
        <repeatableType initiate-test="/event/detail/emergency[@type='Troops In Contact']" cancel-test="/event/detail/emergency[@cancel='true']" _name="TroopsInContact"/>
    </repeater>
    <filter>
        <thumbnail/>
        <urladd host="http://${private_ip}:8080"/>
        <flowtag enable="true" text=""/>
        <streamingbroker enable="true"/>
        <scrubber enable="false" action="overwrite"/>
        <qos>
            <deliveryRateLimiter enabled="true">
                <rateLimitRule clientThresholdCount="500" reportingRateLimitSeconds="200"/>
                <rateLimitRule clientThresholdCount="1000" reportingRateLimitSeconds="300"/>
                <rateLimitRule clientThresholdCount="2000" reportingRateLimitSeconds="400"/>
                <rateLimitRule clientThresholdCount="5000" reportingRateLimitSeconds="800"/>
                <rateLimitRule clientThresholdCount="10000" reportingRateLimitSeconds="1200"/>
            </deliveryRateLimiter>
            <readRateLimiter enabled="false">
                <rateLimitRule clientThresholdCount="500" reportingRateLimitSeconds="200"/>
                <rateLimitRule clientThresholdCount="1000" reportingRateLimitSeconds="300"/>
                <rateLimitRule clientThresholdCount="2000" reportingRateLimitSeconds="400"/>
                <rateLimitRule clientThresholdCount="5000" reportingRateLimitSeconds="800"/>
                <rateLimitRule clientThresholdCount="10000" reportingRateLimitSeconds="1200"/>
            </readRateLimiter>
            <dosRateLimiter enabled="false" intervalSeconds="60">
                <dosLimitRule clientThresholdCount="1" messageLimitPerInterval="60"/>
            </dosRateLimiter>
        </qos>
    </filter>
    <buffer>
        <queue>
            <priority/>
        </queue>
        <latestSA enable="true"/>
    </buffer>
    <dissemination smartRetry="false"/>
    <security>
        <jwt>
            <keystore
                type="PKCS12"
                file="${server_store_rel}"
                password="${cert_pass}"
                keyAlias="${fqdn}"
                keyPassword="${cert_pass}"/>
        </jwt>

        <tls
            keystore="PKCS12"
            keystoreFile="${server_store_rel}"
            keystoreKeyAlias="${fqdn}"
            keystoreKeyPass="${cert_pass}"
            keystorePass="${cert_pass}"
            truststore="JKS"
            truststoreFile="certs/files/01_TRUST/truststore-root.jks"
            truststorePass="${cert_capass}"
            context="TLSv1.2"
            keymanager="SunX509">
            <crl _name="TAKServer CA" crlFile="/opt/tak/certs/files/00_CA/ca.crl"/>
        </tls>
    </security>
    <federation missionFederationDisruptionToleranceRecencySeconds="43200">
        <federation-server port="9000" v1enabled="false" v2port="9001" v2enabled="true" webBaseUrl="https://${fqdn}:8446/Marti">
            <tls
                keystore="PKCS12"
                keystoreFile="${server_store_rel}"
                keystorePass="${cert_pass}"
                keystoreKeyAlias="${fqdn}"
                keystoreKeyPass="${cert_pass}"
                truststore="JKS"
                truststoreFile="certs/files/01_TRUST/fed-truststore.jks"
                truststorePass="${cert_capass}"
                context="TLSv1.2"
                keymanager="SunX509"/>
            <v1Tls tlsVersion="TLSv1.2"/>
            <v1Tls tlsVersion="TLSv1.3"/>
            <federation-token-authentication/>
        </federation-server>
        <fileFilter>
            <fileExtension>pref</fileExtension>
        </fileFilter>
    </federation>
    <plugins/>
    <cluster/>
    <vbm enabled="false"/>
    <certificateSigning CA="TAKServer">
        <certificateConfig>
            <nameEntries>
                <nameEntry name="O" value="${org_xml}"/>
                <nameEntry name="OU" value="${ou_xml}"/>
            </nameEntries>
        </certificateConfig>
        <TAKServerCAConfig
            keystore="PKCS12"
            keystoreFile="certs/files/00_CA/ca-signing.p12"
            keystorePass="${cert_capass}"
            keyAlias="tak-ca"
            validityDays="365"
            signatureAlg="SHA256WithRSA"/>
    </certificateSigning>
</Configuration>
EOF2

  chmod 640 "$out"
  chown tak:tak "$out" 2>/dev/null || true

  sync_martiuser_password "$db_password"
  verify_coreconfig_keystores

  log "wrote $out"
  log "  fqdn=${fqdn}"
  log "  private_ip=${private_ip}"
  log "  server_store=${server_store_rel}"
  log "  public_8446_store=${cert_https_store_rel}"
  log "  server_id=${server_id}"
}

main "$@"
