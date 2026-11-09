#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUNDLE_ROOT="$ROOT"

log() {
  printf '[takserver] %s\n' "$*"
}

fail() {
  printf '[takserver] ERROR: %s\n' "$*" >&2
  exit 1
}

require_root() {
  [ "$(id -u)" -eq 0 ] || fail "must run as root"
}

have_cmd() {
  command -v "$1" >/dev/null 2>&1
}

find_deb() {
  # Clean cattle only: require the release explicitly selected in the bundle.
  TAKSERVER_DEB="$BUNDLE_ROOT/packages/takserver_5.8-RELEASE92_all.deb"
  [ -f "$TAKSERVER_DEB" ] || fail "missing pinned TAK Server 5.8 RELEASE92 deb in bundle"
  return 0
}

find_optional_sig_material() {
  TAK_GPG_KEY="$(find "$BUNDLE_ROOT" -maxdepth 4 -type f -name 'takserver-public-gpg.key' | head -n 1 || true)"
  TAK_DEB_POLICY="$(find "$BUNDLE_ROOT" -maxdepth 4 -type f -name 'deb_policy.pol' | head -n 1 || true)"
}

ensure_pgdg_repo_if_needed() {
  export DEBIAN_FRONTEND=noninteractive
  if apt-cache show postgresql-18 >/dev/null 2>&1 &&
     apt-cache show postgresql-18-postgis-3 >/dev/null 2>&1; then
    log "PostgreSQL 18 and PostGIS 3 available"
    return 0
  fi

  log "enabling PGDG repository for PostgreSQL 18"
  apt-get update -y
  apt-get install -y ca-certificates curl gnupg postgresql-common lsb-release
  install -d /usr/share/postgresql-common/pgdg
  curl -fsSL --retry 5 --retry-all-errors --retry-delay 2 --retry-max-time 180 --connect-timeout 15 --max-time 60 -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
    https://www.postgresql.org/media/keys/ACCC4CF8.asc
  . /etc/os-release
  printf 'deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt %s-pgdg main\n' "$VERSION_CODENAME" \
    > /etc/apt/sources.list.d/pgdg.list
  apt-get update -y
  apt-cache show postgresql-18 >/dev/null 2>&1 || fail "postgresql-18 unavailable"
  apt-cache show postgresql-18-postgis-3 >/dev/null 2>&1 || fail "postgresql-18-postgis-3 unavailable"
}

verify_deb_if_material_present() {
  export DEBIAN_FRONTEND=noninteractive

  if [ -z "${TAK_GPG_KEY:-}" ] || [ -z "${TAK_DEB_POLICY:-}" ]; then
    log "no debsig verification material in bundle; skipping signature verification"
    return 0
  fi

  log "found takserver-public-gpg.key and deb_policy.pol; verifying deb signature"
  apt-get install -y debsig-verify gnupg2

  local deb_policy_id
  deb_policy_id="$(grep -o 'id=\"[^\"]\\+\"' "$TAK_DEB_POLICY" | head -n 1 | sed 's/id="//; s/"$//')"
  [ -n "$deb_policy_id" ] || fail "could not extract debsig policy id from $TAK_DEB_POLICY"

  rm -rf "/usr/share/debsig/keyrings/${deb_policy_id}"
  rm -rf "/etc/debsig/policies/${deb_policy_id}"
  mkdir -p "/usr/share/debsig/keyrings/${deb_policy_id}"
  mkdir -p "/etc/debsig/policies/${deb_policy_id}"

  touch "/usr/share/debsig/keyrings/${deb_policy_id}/debsig.gpg"
  gpg2 --no-default-keyring \
       --keyring "/usr/share/debsig/keyrings/${deb_policy_id}/debsig.gpg" \
       --import "$TAK_GPG_KEY" >/dev/null 2>&1

  cp "$TAK_DEB_POLICY" "/etc/debsig/policies/${deb_policy_id}/debsig.pol"

  debsig-verify "$TAKSERVER_DEB" >/tmp/takserver-debsig.out 2>&1 || {
    cat /tmp/takserver-debsig.out >&2 || true
    fail "debsig verification failed"
  }

  log "debsig verification passed"
}

install_prereqs() {
  export DEBIAN_FRONTEND=noninteractive

  apt-get update -y
  apt-get install -y \
    sudo \
    curl \
    ca-certificates \
    openssl \
    zip \
    unzip \
    uuid-runtime \
    openjdk-17-jdk \
    postgresql-18 \
    postgresql-18-postgis-3
}

install_deb() {
  export DEBIAN_FRONTEND=noninteractive

  log "installing takserver deb: $TAKSERVER_DEB"
  if ! dpkg -i "$TAKSERVER_DEB"; then
    log "dpkg reported issues; running apt-get -f install"
    apt-get install -f -y
    dpkg -i "$TAKSERVER_DEB"
  fi

  dpkg -s takserver >/dev/null 2>&1 || fail "takserver package is not installed"
  log "takserver package installed"
}

reload_init_system() {
  log "reloading init/systemd state"
  systemctl daemon-reload || true
}

start_postgres() {
  if systemctl list-unit-files --type=service --no-pager | grep -q '^postgresql\.service'; then
    systemctl enable postgresql || true
    systemctl restart postgresql || systemctl start postgresql || true
  fi
}

start_takserver() {
  log "deferring takserver start until cert layout + CoreConfig render are complete"
  if systemctl list-unit-files --type=service --no-pager | grep -q '^takserver\.service'; then
    systemctl enable takserver || true
    return 0
  fi

  if [ -x /etc/init.d/takserver ]; then
    update-rc.d takserver defaults >/dev/null 2>&1 || true
    return 0
  fi

  fail "no takserver service found after package install"
}

postcheck() {
  log "dpkg status"
  dpkg -l | awk '/takserver|postgresql-18|postgis/ {print}' | sed 's/^/[takserver]   /' || true

  log "postgresql cluster status"
  if have_cmd pg_lsclusters; then
    pg_lsclusters | sed 's/^/[takserver]   /' || true
  fi

  log "service/unit view"
  systemctl list-unit-files --type=service --no-pager | grep -Ei 'takserver|postgresql' | sed 's/^/[takserver]   /' || true

  log "tak-related processes"
  ps -ef | grep -E 'takserver|takserver-pm|takserver-retention|postgres' | grep -v grep | sed 's/^/[takserver]   /' || true

  log "listening ports"
  ss -ltnp | grep -E '(:8089|:8443|:8446|:9001|:5432)\b' | sed 's/^/[takserver]   /' || true

  log "recent takserver journal"
  journalctl -u takserver -n 80 --no-pager 2>/dev/null | sed 's/^/[takserver]   /' || true

  log "recent syslog errors mentioning tak"
  journalctl -n 120 --no-pager 2>/dev/null | grep -Ei 'tak|postgres|postgis|java' | tail -n 80 | sed 's/^/[takserver]   /' || true
}

main() {
  require_root

  find_deb

  find_optional_sig_material
  ensure_pgdg_repo_if_needed
  verify_deb_if_material_present
  install_prereqs
  install_deb
  reload_init_system
  start_postgres
  start_takserver
  postcheck
  log "takserver install phase complete"
}

main "$@"
