#!/usr/bin/env bash
set -euo pipefail

log() {
  printf '[tak-coreconfig-render] %s\n' "$*"
}

read_trimmed_file() {
  local p="$1"
  [ -f "$p" ] || return 1
  tr -d '\r' < "$p" | sed -e 's/[[:space:]]*$//' | head -n 1
}


read_db_password_file() {
  local p="/etc/taks/db/martiuser_password"
  [ -f "$p" ] || return 1
  tr -d '\r' < "$p" | sed -e 's/[[:space:]]*$//' | head -n 1
}

write_db_password_file() {
  local value="$1"
  install -d -m 700 /etc/taks/db
  umask 077
  printf '%s\n' "$value" > /etc/taks/db/martiuser_password
}

sync_martiuser_password() {
  local pw="$1"
  command -v psql >/dev/null 2>&1 || return 0
  sudo -u postgres psql -d postgres -v ON_ERROR_STOP=1 >/dev/null <<EOF
ALTER ROLE martiuser WITH PASSWORD '${pw}';
EOF
}

read_shell_assignment() {
  local p="$1"
  local key="$2"
  [ -f "$p" ] || return 1
  local v
  v="$(sed -n "s/^${key}=//p" "$p" | head -n 1)"
  [ -n "$v" ] || return 1
  case "$v" in
    \"*\") v="${v#\"}"; v="${v%\"}" ;;
    \'*\') v="${v#\'}"; v="${v%\'}" ;;
  esac
  printf '%s\n' "$v"
}

xml_escape() {
  sed \
    -e 's/&/\&amp;/g' \
    -e 's/"/\&quot;/g' \
    -e "s/'/\&apos;/g" \
    -e 's/</\&lt;/g' \
    -e 's/>/\&gt;/g'
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

main() {
  local bundle_root
  bundle_root="$(cd "$(dirname "$0")/.." && pwd)"

  local node_env="$bundle_root/install/node.env"
  if [ -f "$node_env" ]; then
    # shellcheck disable=SC1090
    . "$node_env"
  fi

  local taks_dir="/etc/taks"
  local db_dir="$taks_dir/db"
  local cert_dir="$taks_dir/certs"
  local cert_meta="/opt/tak/certs/cert-metadata.sh"
  local out="/opt/tak/CoreConfig.xml"
  local server_id_file="$taks_dir/server_id"

  local unit_id fqdn private_ip db_password cert_pass cert_capass org ou org_xml ou_xml
  unit_id="$(read_trimmed_file "$taks_dir/TAKS_UNIT_ID" || true)"
  fqdn="${TAKS_NODE_FQDN:-}"
  private_ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
  db_password="$(read_db_password_file || true)"
  if [ -z "$db_password" ]; then
    db_password="$(extract_db_password || true)"
  fi
  cert_pass="$(read_shell_assignment "$cert_meta" PASS || read_trimmed_file "$cert_dir/PASS" || true)"
  cert_capass="$(read_shell_assignment "$cert_meta" CAPASS || read_trimmed_file "$cert_dir/CAPASS" || true)"
  org="$(read_shell_assignment "$cert_meta" ORGANIZATION || read_trimmed_file "$cert_dir/ORGANIZATION" || true)"
  ou="$(read_shell_assignment "$cert_meta" ORGANIZATIONAL_UNIT || read_trimmed_file "$cert_dir/ORGANIZATIONAL_UNIT" || true)"

  if [ -z "$fqdn" ]; then
    fqdn="$(hostname -f 2>/dev/null || true)"
  fi
  if [ -z "$fqdn" ]; then
    fqdn="$(hostname -s 2>/dev/null || true)"
  fi
  if [ -z "$unit_id" ]; then
    unit_id="$(hostname -s 2>/dev/null || true)"
  fi
  if [ -z "$private_ip" ]; then
    private_ip="127.0.0.1"
  fi
  if [ -z "$db_password" ]; then
    db_password="atakatak"
  fi
  write_db_password_file "$db_password"
  if [ -z "$cert_pass" ]; then
    cert_pass="atakatak"
  fi
  if [ -z "$cert_capass" ]; then
    cert_capass="$cert_pass"
  fi

  mkdir -p "$taks_dir"
  if [ ! -f "$server_id_file" ]; then
    uuidgen | tr -d '\r\n' > "$server_id_file"
  fi

  local server_id
  server_id="$(read_trimmed_file "$server_id_file" || true)"
  if [ -z "$server_id" ]; then
    server_id="$(uuidgen | tr -d '\r\n')"
    printf '%s\n' "$server_id" > "$server_id_file"
  fi

  org_xml="$(printf '%s' "$org" | xml_escape)"
  ou_xml="$(printf '%s' "$ou" | xml_escape)"

  mkdir -p /opt/tak

  cat > "$out" <<EOF2
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Configuration xmlns="http://bbn.com/marti/xml/config">
    <network multicastTTL="5" serverId="${server_id}" version="5.6-RELEASE-6-HEAD">
        <input _name="stdssl" protocol="tls" port="8089" coreVersion="2" clientAuth="true"/>
        <input _name="quic" protocol="quic" port="8090"/>
        <input auth="anonymous" _name="replayudp" protocol="udp" port="6969"/>
        <connector port="8443" _name="https"/>
        <connector port="8444" useFederationTruststore="true" _name="fed_https"/>
        <connector port="8447" clientAuth="false" _name="cert_https"/>
        <announce/>
    </network>
    <auth>
        <File location="UserAuthenticationFile.xml"/>
    </auth>
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
                file="certs/files/02_SERVER/takserver-${unit_id,,}.jks"
                password="${cert_pass}"
                keyAlias="${fqdn}"
                keyPassword="${cert_pass}"/>
        </jwt>

        <tls
            keystore="PKCS12"
            keystoreFile="certs/files/02_SERVER/takserver-${unit_id,,}.jks"
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
        <federation-server port="9000" v1enabled="false" v2port="9001" v2enabled="true" webBaseUrl="https://${fqdn}:8443/Marti">
            <tls
                keystore="PKCS12"
                keystoreFile="certs/files/02_SERVER/takserver-${unit_id,,}.jks"
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
  sync_martiuser_password "$db_password" || true
  log "wrote $out"
  log "  fqdn=${fqdn}"
  log "  private_ip=${private_ip}"
  log "  unit_id=${unit_id}"
  log "  server_id=${server_id}"
}

main "$@"
