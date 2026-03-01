#!/usr/bin/env bash
set -euo pipefail

echo "## Route sanity check: no duplicate (method,path)"

PYTHONPATH=/opt/tak-orch/orchestrator /opt/tak-orch/.venv/bin/python3 -c '
import sys
from orchestrator_api.app import app

routes = {}
for r in app.router.routes:
    path = getattr(r, "path", None)
    methods = getattr(r, "methods", None)
    endpoint = getattr(r, "endpoint", None)
    if not path or not methods:
        continue
    for m in methods:
        if m == "HEAD":
            continue
        routes.setdefault((m, path), []).append(endpoint)

dupes = {k:v for k,v in routes.items() if len(v) > 1}
if dupes:
    print("ERROR: duplicate routes detected:", file=sys.stderr)
    for (m,p), eps in sorted(dupes.items()):
        print(f"  {m} {p}", file=sys.stderr)
        for e in eps:
            print(f"    -> {e.__module__}.{e.__qualname__}", file=sys.stderr)
    sys.exit(1)

print("OK: no duplicate routes.")
'
