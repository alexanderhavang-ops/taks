#!/usr/bin/env bash
# Install the TAK-specific LDAP auxiliary schema from TAK Server 5.8 RELEASE92
# LDAP package (03-setup-tak-schema.sh), using host-native cn=config.
set -euo pipefail

[ "$(id -u)" -eq 0 ] || { echo "TAK LDAP schema requires root" >&2; exit 1; }
command -v ldapsearch >/dev/null
command -v ldapadd >/dev/null

# The add is idempotent; do not clobber cn=config or ignore unexpected failures.
if ldapsearch -LLL -Q -Y EXTERNAL -H ldapi:/// -b cn=schema,cn=config \
    '(olcObjectClasses=*takUser*)' dn 2>/dev/null | grep -q '^dn:'; then
  echo "[tak-ldap-schema] takUser schema already present"
  exit 0
fi

tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT
cat > "$tmp" <<'EOF_LDIF'
dn: cn=tak,cn=schema,cn=config
objectClass: olcSchemaConfig
cn: tak
olcAttributeTypes: ( 1.3.6.1.4.1.20807.825.1000.1 NAME 'takRole' EQUALITY caseIgnoreMatch SUBSTR caseIgnoreSubstringsMatch SYNTAX 1.3.6.1.4.1.1466.115.121.1.15 )
olcAttributeTypes: ( 1.3.6.1.4.1.20807.825.1000.2 NAME 'takCallSign' EQUALITY caseIgnoreMatch SUBSTR caseIgnoreSubstringsMatch SYNTAX 1.3.6.1.4.1.1466.115.121.1.15 )
olcAttributeTypes: ( 1.3.6.1.4.1.20807.825.1000.3 NAME 'takColor' EQUALITY caseIgnoreMatch SUBSTR caseIgnoreSubstringsMatch SYNTAX 1.3.6.1.4.1.1466.115.121.1.15 )
olcObjectClasses: ( 1.3.6.1.4.1.20807.825.1000.4 NAME 'takUser' DESC 'TAK User' SUP top AUXILIARY MAY ( takRole $ takCallSign $ takColor $ c ) )
EOF_LDIF
ldapadd -Q -Y EXTERNAL -H ldapi:/// -f "$tmp"
ldapsearch -LLL -Q -Y EXTERNAL -H ldapi:/// -b cn=schema,cn=config \
  '(olcObjectClasses=*takUser*)' dn | grep -q '^dn:' || {
    echo "[tak-ldap-schema] schema verification failed" >&2
    exit 1
  }
echo "[tak-ldap-schema] TAK schema installed and verified"
