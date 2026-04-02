#!/usr/bin/env bash
set -euo pipefail

PHASE="${1:-phase2}"
DOMAIN="${2:-all}"

if [[ "$PHASE" != "phase2" && "$PHASE" != "phase3" ]]; then
  echo "usage: $0 <phase2|phase3> [domain|all]" >&2
  exit 2
fi

export PYTHONPATH="/opt/tak/tools/takctl:/opt/tak/tools/martine:/opt/taks/takctl:/opt/taks/martine"

sudo -u tak env   PYTHONPATH="$PYTHONPATH"   /opt/tak/tools/takctl/.venv/bin/python3 - "$PHASE" "$DOMAIN" <<'PY'
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from takctl.config import load_config as load_takctl_config
from takctl.services.llm3.domain_config import discover_enabled_domains, load_domain_config, phase_enabled
from takctl.services.llm3.runner import run_phase2, run_phase3

phase = sys.argv[1]
domain_arg = sys.argv[2]

def jdump(x):
    return json.dumps(x, ensure_ascii=False, indent=2, sort_keys=True)

cfg = load_takctl_config()
infra_dir = Path(str(cfg.get("llm_infra_dir", "/opt/tak/tools/takctl/llm-infra")))

if domain_arg == "all":
    domains = []
    for d in discover_enabled_domains(infra_dir):
        try:
            dc = load_domain_config(infra_dir, d)
        except Exception:
            continue
        if phase_enabled(dc, phase):
            domains.append(d)
else:
    domains = [domain_arg]

if not domains:
    print(f"no enabled domains for {phase}")
    sys.exit(1)

overall_ok = True
started = time.time()

print(f"## llm3 {phase}")
print(f"## domains: {', '.join(domains)}")
print()

for idx, dom in enumerate(domains, start=1):
    print("============================================================")
    print(f"## [{idx}/{len(domains)}] start {dom} {phase}")
    dom_t0 = time.time()

    if phase == "phase2":
        out = run_phase2(domain=dom)
        dom_res = ((out.get("domains") or {}).get(dom) or {})
        trace_dir = str(dom_res.get("trace_dir") or "")
        findings = dom_res.get("findings") if isinstance(dom_res.get("findings"), dict) else {}
        err = str(dom_res.get("error") or "")
        ok = bool(dom_res.get("ok"))
        print(f"ok: {str(ok).lower()}")
        print(f"trace_dir: {trace_dir}")
        if findings:
            print("important:", str(findings.get("important") or "")[:500])
            print("newest:", str(findings.get("newest") or "")[:500])
        if err:
            print("error:", err)

    else:
        out = run_phase3(domain=dom)
        dom_res = ((out.get("domains") or {}).get(dom) or {})
        ok = bool(dom_res.get("ok"))
        errs = dom_res.get("errors") or []
        print(f"ok: {str(ok).lower()}")
        print("errors:", jdump(errs))
        card = dom_res.get("card") if isinstance(dom_res.get("card"), dict) else {}
        detail = dom_res.get("detail") if isinstance(dom_res.get("detail"), dict) else {}
        if card:
            print("card keys:", ", ".join(sorted(card.keys())))
        if detail:
            print("detail keys:", ", ".join(sorted(detail.keys())))

    run_id = str(out.get("run_id") or "")
    print(f"run_id: {run_id}")

    # Inspect trace dir(s) for this domain/phase and summarize iterations/tools.
    trace_root = Path("/opt/tak/tools/martine/state/logs")
    traces = sorted(trace_root.glob(f"{run_id}-{dom}-{phase}*"))
    if traces:
        for td in traces:
            prompt_n = len(list(td.glob("*_prompt.txt")))
            llm_n = len(list(td.glob("*_llm.json")))
            parsed_n = len(list(td.glob("*_parsed.json")))
            tool_n = len(list(td.glob("*_tool.json")))
            print(f"trace: {td}")
            print(f"  prompts={prompt_n} llm={llm_n} parsed={parsed_n} tools={tool_n}")
            tool_files = sorted(td.glob("*_tool.json"))
            for tf in tool_files:
                try:
                    obj = json.loads(tf.read_text(encoding="utf-8"))
                    print(f"  tool: {obj.get('tool_name')}")
                except Exception as e:
                    print(f"  tool: <parse-failed {type(e).__name__}: {e}>")
    else:
        print("trace: <none found>")

    dt = time.time() - dom_t0
    print(f"## [{idx}/{len(domains)}] done {dom} {phase} in {dt:.1f}s")
    print()

    if not bool(((out.get("domains") or {}).get(dom) or {}).get("ok")):
        overall_ok = False

total_dt = time.time() - started
print("============================================================")
print(f"## done {phase} total {total_dt:.1f}s")
print(f"ok: {str(overall_ok).lower()}")

sys.exit(0 if overall_ok else 1)
PY
