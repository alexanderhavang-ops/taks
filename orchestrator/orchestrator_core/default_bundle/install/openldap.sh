#!/usr/bin/env bash
set -euo pipefail

log() {
  printf '[openldap] %s\n' "$*"
}

die() {
  printf '[openldap] ERROR: %s\n' "$*" >&2
  exit 1
}

read_simple_kv_optional() {
  local path="$1"
  local key="$2"
  [ -f "$path" ] || return 1
  sed -n "s/^[[:space:]]*${key}[[:space:]]*=[[:space:]]*//p" "$path" | head -n 1 | sed -e 's/[[:space:]]*$//'
}

strip_quotes() {
  local s="${1:-}"
  s="$(printf '%s' "$s" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
  case "$s" in
    \"*\") s="${s#\"}"; s="${s%\"}" ;;
    \'*\') s="${s#\'}"; s="${s%\'}" ;;
  esac
  printf '%s' "$s"
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
      strip_quotes "$v"
      return 0
    fi
  done
  return 1
}

cfg() {
  local key="$1"
  local default="${2:-}"
  local v=""
  v="$(read_kv_first_hit_in_dir /opt/tak/tools/takctl/conf.d "$key" || true)"
  [ -n "$v" ] || v="$(read_simple_kv_optional /etc/taks/ldap.conf "$key" 2>/dev/null | sed -e 's/[[:space:]]*$//' || true)"
  [ -n "$v" ] || v="$(read_kv_first_hit_in_dir /etc/taks-bootstrap.d/config.d "$key" || true)"
  [ -n "$v" ] || v="$default"
  strip_quotes "$v"
}

secret() {
  local key="$1"
  local default="${2:-}"
  local v=""
  v="$(read_kv_first_hit_in_dir /opt/tak/tools/takctl/secrets.d "$key" || true)"
  [ -n "$v" ] || v="$(read_simple_kv_optional /etc/taks/ldap-secrets.conf "$key" 2>/dev/null | sed -e 's/[[:space:]]*$//' || true)"
  [ -n "$v" ] || v="$(read_kv_first_hit_in_dir /etc/taks-bootstrap.d/secrets.d "$key" || true)"
  [ -n "$v" ] || v="$default"
  strip_quotes "$v"
}

rand_pw() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -base64 36 | tr -d '\n'
    return 0
  fi
  python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(32))
PY
}

domain_from_base_dn() {
  local base="$1"
  local out=""
  local IFS=','
  local part val
  for part in $base; do
    part="$(printf '%s' "$part" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
    case "$part" in
      dc=*|DC=*)
        val="${part#*=}"
        out="${out:+$out.}$val"
        ;;
    esac
  done
  printf '%s' "${out:-taks.local}"
}

first_dc_from_base_dn() {
  local base="$1"
  local IFS=','
  local part
  for part in $base; do
    part="$(printf '%s' "$part" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
    case "$part" in
      dc=*|DC=*) printf '%s' "${part#*=}"; return 0 ;;
    esac
  done
  printf 'taks'
}

write_runtime_files() {
  local uri="$1" base="$2" people="$3" groups="$4" services="$5" service_dn="$6" admin_dn="$7" service_pw="$8" admin_pw="$9"
  mkdir -p /etc/taks
  chmod 0755 /etc/taks

  {
    printf 'ldap_admin_password = %s\n' "$admin_pw"
    printf 'ldap_service_account_password = %s\n' "$service_pw"
  } > /etc/taks/ldap-secrets.conf
  chmod 0600 /etc/taks/ldap-secrets.conf

  {
    printf 'backing_user_store = ldap\n'
    printf 'ldap_uri = %s\n' "$uri"
    printf 'ldap_base_dn = %s\n' "$base"
    printf 'ldap_people_ou = %s\n' "$people"
    printf 'ldap_groups_ou = %s\n' "$groups"
    printf 'ldap_services_ou = %s\n' "$services"
    printf 'ldap_service_account_dn = %s\n' "$service_dn"
    printf 'ldap_admin_dn = %s\n' "$admin_dn"
    printf 'ldap_user_string = uid={username},ou=%s,%s\n' "$people" "$base"
  } > /etc/taks/ldap.conf
  chmod 0644 /etc/taks/ldap.conf

  # Make generated node-local LDAP settings visible to later tak-installer/takctl
  # phases. Those phases run after OpenLDAP provisioning and may not be able to
  # read root-only /etc/taks/ldap-secrets.conf directly.
  install -d -m 0755 /opt/tak/tools/takctl/conf.d
  install -m 0644 /etc/taks/ldap.conf /opt/tak/tools/takctl/conf.d/ldap.conf

  if getent group tak >/dev/null 2>&1; then
    install -d -m 0750 -o root -g tak /opt/tak/tools/takctl/secrets.d
    install -m 0640 -o root -g tak /etc/taks/ldap-secrets.conf /opt/tak/tools/takctl/secrets.d/ldap.conf
  else
    install -d -m 0700 /opt/tak/tools/takctl/secrets.d
    install -m 0600 /etc/taks/ldap-secrets.conf /opt/tak/tools/takctl/secrets.d/ldap.conf
  fi

  # Also publish node-local generated values into the runtime bootstrap overlay
  # so takctl-config and other installer actions see the same non-empty values.
  install -d -m 0755 /etc/taks-bootstrap.d/config.d
  install -d -m 0755 /etc/taks-bootstrap.d/secrets.d
  install -m 0644 /etc/taks/ldap.conf /etc/taks-bootstrap.d/config.d/ldap.conf
  install -m 0600 /etc/taks/ldap-secrets.conf /etc/taks-bootstrap.d/secrets.d/ldap.conf
}

ldap_base_exists() {
  local uri="$1" admin_dn="$2" admin_pw="$3" dn="$4"
  ldapsearch -LLL -x -H "$uri" -D "$admin_dn" -w "$admin_pw" -b "$dn" -s base dn >/dev/null 2>&1
}

ldap_add_if_missing() {
  local uri="$1" admin_dn="$2" admin_pw="$3" dn="$4" ldif="$5"
  if ldap_base_exists "$uri" "$admin_dn" "$admin_pw" "$dn"; then
    return 0
  fi
  printf '%s\n' "$ldif" | ldapadd -x -H "$uri" -D "$admin_dn" -w "$admin_pw"
}

reset_olc_rootpw() {
  local base="$1" admin_pw="$2"
  local db_dn admin_hash tmp

  db_dn="$(
    ldapsearch -Q -Y EXTERNAL -H ldapi:/// -LLL -b cn=config "(olcSuffix=${base})" dn 2>/dev/null \
      | sed -n 's/^dn: //p' | head -n 1
  )"

  [ -n "$db_dn" ] || die "could not find slapd config database for suffix $base"

  admin_hash="$(slappasswd -s "$admin_pw")"
  tmp="$(mktemp)"
  cat > "$tmp" <<EOF_LDIF
dn: ${db_dn}
changetype: modify
replace: olcRootPW
olcRootPW: ${admin_hash}
EOF_LDIF

  ldapmodify -Q -Y EXTERNAL -H ldapi:/// -f "$tmp" >/tmp/taks-openldap-rootpw.log 2>&1 || {
    cat /tmp/taks-openldap-rootpw.log >&2 || true
    rm -f "$tmp"
    die "failed to reset LDAP root password"
  }

  rm -f "$tmp"
}

seed_directory() {
  local uri="$1" base="$2" people="$3" groups="$4" services="$5" service_dn="$6" admin_dn="$7" service_pw="$8" admin_pw="$9"
  local base_dc service_hash

  base_dc="$(first_dc_from_base_dn "$base")"
  service_hash="$(slappasswd -s "$service_pw")"

  : > /tmp/taks-openldap-seed.log

  ldap_add_if_missing "$uri" "$admin_dn" "$admin_pw" "$base" \
"dn: ${base}
objectClass: top
objectClass: dcObject
objectClass: organization
o: TAKS
dc: ${base_dc}" >>/tmp/taks-openldap-seed.log 2>&1 || true

  ldap_add_if_missing "$uri" "$admin_dn" "$admin_pw" "ou=${people},${base}" \
"dn: ou=${people},${base}
objectClass: top
objectClass: organizationalUnit
ou: ${people}" >>/tmp/taks-openldap-seed.log 2>&1 || true

  ldap_add_if_missing "$uri" "$admin_dn" "$admin_pw" "ou=${groups},${base}" \
"dn: ou=${groups},${base}
objectClass: top
objectClass: organizationalUnit
ou: ${groups}" >>/tmp/taks-openldap-seed.log 2>&1 || true

  ldap_add_if_missing "$uri" "$admin_dn" "$admin_pw" "ou=${services},${base}" \
"dn: ou=${services},${base}
objectClass: top
objectClass: organizationalUnit
ou: ${services}" >>/tmp/taks-openldap-seed.log 2>&1 || true

  if ldap_base_exists "$uri" "$admin_dn" "$admin_pw" "$service_dn"; then
    cat >/tmp/taks-openldap-service-account.ldif <<EOF_LDIF
dn: ${service_dn}
changetype: modify
replace: userPassword
userPassword: ${service_hash}
EOF_LDIF
    ldapmodify -x -H "$uri" -D "$admin_dn" -w "$admin_pw" -f /tmp/taks-openldap-service-account.ldif >>/tmp/taks-openldap-seed.log 2>&1 || true
  else
    cat >/tmp/taks-openldap-service-account.ldif <<EOF_LDIF
dn: ${service_dn}
objectClass: simpleSecurityObject
objectClass: organizationalRole
cn: taksvc
description: TAK Server/takctl LDAP service account
userPassword: ${service_hash}
EOF_LDIF
    ldapadd -x -H "$uri" -D "$admin_dn" -w "$admin_pw" -f /tmp/taks-openldap-service-account.ldif >>/tmp/taks-openldap-seed.log 2>&1 || true
  fi
}

main() {
  [ "$(id -u)" -eq 0 ] || die "must run as root"

  local store manage uri base people groups services service_dn admin_dn service_pw admin_pw domain
  store="$(cfg backing_user_store userauthfile | tr '[:upper:]' '[:lower:]')"
  case "$store" in
    ldap|ldap_local|openldap) ;;
    *) log "skip; backing_user_store=$store"; exit 0 ;;
  esac

  uri="$(cfg ldap_uri ldap://127.0.0.1:389)"
  manage="$(cfg ldap_manage_local true | tr '[:upper:]' '[:lower:]')"
  case "$uri" in
    ldap://127.0.0.1:*|ldap://localhost:*|ldapi://*) ;;
    *) log "LDAP URI is not loopback ($uri); assuming external/shared LDAP"; exit 0 ;;
  esac
  case "$manage" in
    false|0|no|off) log "skip local provisioning; ldap_manage_local=$manage"; exit 0 ;;
  esac

  base="$(cfg ldap_base_dn dc=taks,dc=local)"
  people="$(cfg ldap_people_ou people)"
  groups="$(cfg ldap_groups_ou groups)"
  services="$(cfg ldap_services_ou services)"
  service_dn="$(cfg ldap_service_account_dn "cn=taksvc,ou=${services},${base}")"
  admin_dn="$(cfg ldap_admin_dn "cn=admin,${base}")"
  service_pw="$(secret ldap_service_account_password '')"
  admin_pw="$(secret ldap_admin_password '')"
  [ -n "$service_pw" ] || service_pw="$(rand_pw)"
  [ -n "$admin_pw" ] || admin_pw="$(rand_pw)"
  domain="$(domain_from_base_dn "$base")"

  export DEBIAN_FRONTEND=noninteractive
  debconf-set-selections <<EOF_DEBCONF
slapd slapd/no_configuration boolean false
slapd slapd/domain string ${domain}
slapd shared/organization string TAKS
slapd slapd/password1 password ${admin_pw}
slapd slapd/password2 password ${admin_pw}
slapd slapd/backend select MDB
slapd slapd/purge_database boolean false
slapd slapd/move_old_database boolean true
slapd slapd/allow_ldap_v2 boolean false
EOF_DEBCONF

  apt-get update
  apt-get install -y slapd ldap-utils
  dpkg-reconfigure -f noninteractive slapd >/tmp/taks-openldap-reconfigure.log 2>&1 || true
  systemctl enable --now slapd >/dev/null 2>&1 || service slapd start || true

  write_runtime_files "$uri" "$base" "$people" "$groups" "$services" "$service_dn" "$admin_dn" "$service_pw" "$admin_pw"

  reset_olc_rootpw "$base" "$admin_pw"

  if ! ldapsearch -LLL -x -H "$uri" -D "$admin_dn" -w "$admin_pw" -b "$base" -s base dn >/dev/null 2>&1; then
    die "LDAP admin bind failed after root password reset; see /tmp/taks-openldap-rootpw.log"
  fi

  seed_directory "$uri" "$base" "$people" "$groups" "$services" "$service_dn" "$admin_dn" "$service_pw" "$admin_pw"

  if ldapsearch -LLL -x -H "$uri" -D "$service_dn" -w "$service_pw" -b "$base" -s base dn >/dev/null 2>&1; then
    log "initialized local LDAP at $base"
    exit 0
  fi

  die "LDAP service account bind failed after provisioning; see /tmp/taks-openldap-seed.log and /tmp/taks-openldap-reconfigure.log"
}

main "$@"
