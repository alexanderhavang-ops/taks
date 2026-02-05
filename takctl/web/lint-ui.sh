#!/usr/bin/env bash
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

STRICT=0
if [[ "${1:-}" == "--strict" ]]; then STRICT=1; fi

need_file() { [[ -f "$1" ]] || { echo "❌ missing file: $1"; exit 1; }; }
have() { command -v "$1" >/dev/null 2>&1; }

echo "## cwd: $(pwd)"
echo "## strict: $STRICT"
echo

echo "## 0) files sanity"
need_file index.html
need_file splash.html
need_file splash.js
need_file splash.css
ls -l css/*.css >/dev/null
echo "✅ files present"
echo

# ------------------------------------------------------------
# 1) HTML checks
# ------------------------------------------------------------
echo "## 1) HTML checks"

if have tidy; then
  echo "# tidy (strict) index.html"
  tidy -q -e index.html || { echo "❌ HTML errors in index.html"; exit 1; }
  echo "✅ index.html ok"
else
  echo "⚠️  SKIP: tidy not installed (airgapped/offline ok)."
fi

if have tidy; then
  echo
  echo "# tidy (fragment/non-fatal) splash.html"
  tidy -q -errors splash.html || true
  echo "✅ splash.html ok (fragment mode)"
else
  echo "⚠️  SKIP: splash.html fragment check (tidy not installed)."
fi

if have htmlhint; then
  echo
  echo "# htmlhint index.html"
  htmlhint index.html || { echo "❌ htmlhint errors in index.html"; exit 1; }
  echo "✅ htmlhint index.html ok"
else
  echo "⚠️  SKIP: htmlhint not installed."
fi

echo

# ------------------------------------------------------------
# 2) CSS lint (optional, non-blocking unless --strict)
# ------------------------------------------------------------
echo "## 2) CSS lint (optional)"

if have node && have stylelint; then
  NODEV="$(node -p 'process.versions.node' 2>/dev/null || true)"
  echo "node version: ${NODEV:-unknown}"

  if node -e 'const [a]=process.versions.node.split(".").map(Number); process.exit(a>=14?0:2)'; then
    CFG="./.stylelintrc.json"
    if [[ ! -f "$CFG" ]]; then
      echo "⚠️  SKIP: $CFG not found (create takctl/web/.stylelintrc.json)."
    else
      if stylelint --config "$CFG" splash.css css/*.css; then
        echo "✅ CSS ok (stylelint)"
      else
        if [[ "$STRICT" -eq 1 ]]; then
          echo "❌ CSS lint errors (strict mode)"
          exit 1
        fi
        echo "⚠️  CSS lint errors (non-fatal; run with --strict to fail)"
      fi
    fi
  else
    echo "⚠️  SKIP: Node too old for stylelint (need >=14)."
  fi
else
  echo "⚠️  SKIP: node/stylelint not installed (airgapped/offline ok)."
fi

echo

# ------------------------------------------------------------
# 3) JS syntax check (optional)
# ------------------------------------------------------------
echo "## 3) JS syntax (optional)"
if have node; then
  node --check splash.js || { echo "❌ JS syntax error"; exit 1; }
  echo "✅ JS ok"
else
  echo "⚠️  SKIP: node not installed (airgapped/offline ok)."
fi

echo
echo "✅ UI lint passed (best-effort)"
