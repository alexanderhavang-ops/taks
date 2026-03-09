#!/usr/bin/env bash
set -euo pipefail

PY="/opt/tak/tools/takctl/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "ERROR: python not found: $PY" >&2
  exit 1
fi

export PYTHONPATH="/opt/taks/takctl:${PYTHONPATH:-}"
exec "$PY" -m takctl.cli.import_users "$@"
