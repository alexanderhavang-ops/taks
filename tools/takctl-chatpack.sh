#!/usr/bin/env bash
set -euo pipefail

# tools/takctl-chatpack.sh
#
# Generate a single Markdown bundle you can paste into a fresh ChatGPT chat.
# Goals:
#   - Paste-safe: NO heredocs/EOF, minimal quoting, deterministic output
#   - Include: architecture/wiring notes + selected code/config files
#   - Exclude: backups, ignite work dirs, secrets, vendor/minified JS
#   - Keep: takctl/takctl/services.crl
#
# Usage:
#   ./tools/takctl-chatpack.sh > /tmp/takctl-context.md
#   ./tools/takctl-chatpack.sh --out /tmp/takctl-context.md
#   ./tools/takctl-chatpack.sh --with-runtime --out /tmp/takctl-context+runtime.md
#
# Env:
#   MAX_BYTES per-file max bytes (default 200k)
#   MAX_FILES max files included (default 250)

VERSION="2026-02-01.4"

OUT=""
WITH_RUNTIME=0
MAX_BYTES="${MAX_BYTES:-200000}"
MAX_FILES="${MAX_FILES:-250}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage() {
  printf '%s\n' "Usage: takctl-chatpack.sh [--out FILE] [--with-runtime]"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --out)
      OUT="${2:-}"
      shift 2
      ;;
    --with-runtime)
      WITH_RUNTIME=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf '%s\n' "Unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

# Write to OUT if set; else stdout
w() {
  if [[ -n "$OUT" ]]; then
    cat >>"$OUT"
  else
    cat
  fi
}

# Basic redaction (best-effort; do not rely on this alone)
redact_stream() {
  sed -E \
    -e 's/((pass(word)?|storepass|secret|token|api[_-]?key)[[:space:]]*[:=][[:space:]]*)[^[:space:]]+/\1***REDACTED***/Ig' \
    -e '/BEGIN (EC |RSA )?PRIVATE KEY/,/END (EC |RSA )?PRIVATE KEY/d' \
    -e '/BEGIN PRIVATE KEY/,/END PRIVATE KEY/d' \
    -e '/BEGIN CERTIFICATE/,/END CERTIFICATE/d' \
    -e '/BEGIN OPENSSH PRIVATE KEY/,/END OPENSSH PRIVATE KEY/d'
}

# Robust: consider file "binary" only if it contains NUL byte.
is_text_file() {
  # grep -q $'\x00' returns 0 if NUL found => binary
  if LC_ALL=C grep -q $'\x00' "$1" 2>/dev/null; then
    return 1
  fi
  return 0
}

print_header() {
  {
    printf '%s\n' "# takctl context bundle"
    printf '\n'
    printf '%s\n' "Generated: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
    printf '%s\n' "Version: ${VERSION}"
    printf '%s\n' "Repo root: ${REPO_ROOT}"
    printf '\n'
    printf '%s\n' "Paste this entire document into a new chat to restore takctl context."
    printf '\n'
  } | w
}

print_architecture_notes() {
  {
    printf '%s\n' "## Architecture / wiring (human notes)"
    printf '\n'
    printf '%s\n' "Read this section first in a fresh chat."
    printf '\n'

    printf '%s\n' "### Components"
    printf '%s\n' "- takctl: Python CLI (Typer) + services layer that reads TAK artifacts (DB + XML + CRL) and can invoke helper scripts."
    printf '%s\n' "- takctl-web: FastAPI backend (uvicorn) that serves JSON APIs + static UI."
    printf '%s\n' "- nginx: reverse proxy exposing the takctl UI/API under the main TLS vhost path /takctl/."
    printf '\n'

    printf '%s\n' "### Ports / URLs (current wiring, expected)"
    printf '%s\n' "- Local backend: http://127.0.0.1:8080/ (uvicorn FastAPI)"
    printf '%s\n' "- Public: https://46hvbat.tak-hv-sandbox.se/takctl/ (nginx proxies to 127.0.0.1:8080)"
    printf '%s\n' "- Enrollment: nginx listens on 8446 and proxies to TAK server on https://127.0.0.1:8447/ for /Marti/... enrollment API + WebTAK"
    printf '\n'

    printf '%s\n' "### takctl-web API endpoints (expected)"
    printf '%s\n' "- /api/health -> JSON {ok:true}"
    printf '%s\n' "- /api/crl/status -> CRL existence, mtime, revoked count, sample serials"
    printf '%s\n' "- /api/clients -> read-only TAK DB clients (callsigns/uids/last_seen)"
    printf '%s\n' "- /api/certs -> read-only TAK DB certs (revoked flags, serials)"
    printf '%s\n' "- /api/users and /api/users/{username} -> READ ONLY from UserAuthenticationFile.xml (no Java in read path)"
    printf '\n'

    printf '%s\n' "### User auth XML behavior (important assumptions)"
    printf '%s\n' "- takctl.services.userauth_file resolves the auth XML path by parsing CoreConfig.xml."
    printf '%s\n' "- It looks specifically under the auth block for a File node with a location attribute."
    printf '%s\n' "- Relative locations are resolved relative to the directory containing CoreConfig.xml (usually /opt/tak/)."
    printf '%s\n' "- Usernames are typically in a User element attribute identifier=... in UserAuthenticationFile.xml."
    printf '\n'

    printf '%s\n' "### CRL signing / cert behavior (current approach)"
    printf '%s\n' "- CRL file is expected at a known path (example observed: /opt/tak/certs/files/ca.crl)."
    printf '%s\n' "- takctl keeps a CRL preflight/sanity check to fail fast with actionable errors."
    printf '\n'

    printf '%s\n' "### Privileges / runtime model"
    printf '%s\n' "- takctl-web.service runs under systemd (should be a non-root user, commonly tak)."
    printf '%s\n' "- Read paths should not require sudo."
    printf '%s\n' "- Write paths (UserManager.jar usermod/certmod, CRL signing) may require controlled sudo helpers (takctl-usermgr, takctl-crl-sign)."
    printf '\n'

    printf '%s\n' "### Known pitfalls we already hit"
    printf '%s\n' "- Do not pass the auth XML path into functions expecting a CoreConfig.xml path."
    printf '%s\n' "- Nginx prefixing: /takctl/ must map to backend / (trailing slash matters)."
    printf '\n'
  } | w
}

# Build file list: tracked if possible, else find
list_files() {
  ( cd "$REPO_ROOT" && {
      if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        git ls-files
      else
        find . -type f | sed 's|^\./||'
      fi
    } ) \
  | sed 's|^\./||' \
  | sort
}

# Exclusion filters. Keep takctl/takctl/services.crl explicitly.
filter_files() {
  while IFS= read -r p; do
    [[ -n "$p" ]] || continue

    # Always keep this special case
    if [[ "$p" == "takctl/takctl/services.crl" ]]; then
      printf '%s\n' "$p"
      continue
    fi

    case "$p" in
      takctl/backup/*) continue ;;
      takctl/ignite/work/*) continue ;;
      takctl/secrets/*) continue ;;
      */node_modules/*) continue ;;
      */__pycache__/*) continue ;;
      *.pyc) continue ;;
      */vendor/*) continue ;;
      *.min.js) continue ;;
      *.p12|*.jks|*.key|*.pem|*.crt|*.csr|*.crl) continue ;; # real secrets/certs excluded
    esac

    # Skip ignite marshaller blobs if they sneak through
    if [[ "$p" == *"marshaller"*".classname0" ]]; then
      continue
    fi

    printf '%s\n' "$p"
  done
}

print_repo_tree() {
  {
    printf '%s\n' "## Repository tree (filtered, tracked when possible)"
    printf '\n'
    list_files | filter_files | sed -n '1,600p'
    printf '\n'
  } | w
}

emit_file_md() {
  local rel="$1"
  local abs="$REPO_ROOT/$rel"

  [[ -f "$abs" ]] || return 0

  local sz
  sz="$(wc -c <"$abs" 2>/dev/null || echo 0)"
  if [[ "$sz" -gt "$MAX_BYTES" ]]; then
    {
      printf '%s\n' "### \`$rel\` (skipped: ${sz} bytes > MAX_BYTES=${MAX_BYTES})"
      printf '\n'
    } | w
    return 0
  fi

  if ! is_text_file "$abs"; then
    {
      printf '%s\n' "### \`$rel\` (skipped: contains NUL byte; likely binary)"
      printf '\n'
    } | w
    return 0
  fi

  local lang=""
  case "$rel" in
    *.py) lang="python" ;;
    *.sh) lang="bash" ;;
    *.conf) lang="nginx" ;;
    *.service) lang="ini" ;;
    *.toml) lang="toml" ;;
    *.xml) lang="xml" ;;
    *.js) lang="javascript" ;;
    *.css) lang="css" ;;
    *.md) lang="markdown" ;;
    *) lang="" ;;
  esac

  {
    printf '%s\n' "### \`$rel\`"
    printf '\n'
    if [[ -n "$lang" ]]; then
      printf '%s\n' "\`\`\`${lang}"
    else
      printf '%s\n' "\`\`\`"
    fi
    # redact is best-effort; still review before pasting publicly
    redact_stream <"$abs"
    printf '\n%s\n' "\`\`\`"
    printf '\n'
  } | w
}

print_selected_files() {
  {
    printf '%s\n' "## Key files (contents)"
    printf '\n'
  } | w

  local count=0

  # Prioritize: infra wiring + backend + services + tests + scripts
  while IFS= read -r rel; do
    emit_file_md "$rel"
    count=$((count+1))
    if [[ "$count" -ge "$MAX_FILES" ]]; then
      {
        printf '%s\n' "_Truncated: reached MAX_FILES=${MAX_FILES}_"
        printf '\n'
      } | w
      break
    fi
  done < <(
    list_files | filter_files \
      | grep -E '^(infra/|takctl/takctl/|takctl/tests/|takctl/bin/|tools/|takctl/pyproject\.toml|takctl/takctl\.conf)' \
      | grep -vE '^takctl/web/vendor/' \
      | sort
  )
}

print_runtime_snapshot() {
  [[ "$WITH_RUNTIME" -eq 1 ]] || return 0

  {
    printf '%s\n' "## Runtime snapshot (sanitized)"
    printf '\n'
    printf '%s\n' "Collected: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
    printf '\n'

    printf '%s\n' "### systemd: takctl-web.service (short)"
    printf '%s\n' "\`\`\`"
    systemctl --no-pager -l status takctl-web.service 2>/dev/null | sed -n '1,80p' | redact_stream || true
    printf '%s\n' "\`\`\`"
    printf '\n'

    printf '%s\n' "### nginx: sites-enabled listing"
    printf '%s\n' "\`\`\`"
    ls -l /etc/nginx/sites-enabled 2>/dev/null | redact_stream || true
    printf '%s\n' "\`\`\`"
    printf '\n'

    printf '%s\n' "### takctl-web: openapi paths (best-effort)"
    printf '%s\n' "\`\`\`"
    if command -v curl >/dev/null 2>&1 && command -v python3 >/dev/null 2>&1; then
      curl -fsS http://127.0.0.1:8080/openapi.json 2>/dev/null \
        | python3 -c 'import json,sys; j=json.load(sys.stdin); [print(p) for p in sorted(j.get("paths",{}).keys())]' \
        2>/dev/null || true
    fi
    printf '%s\n' "\`\`\`"
    printf '\n'
  } | w
}

main() {
  if [[ -n "$OUT" ]]; then
    : >"$OUT"
  fi

  print_header
  print_architecture_notes
  print_repo_tree
  print_selected_files
  print_runtime_snapshot
}

main

