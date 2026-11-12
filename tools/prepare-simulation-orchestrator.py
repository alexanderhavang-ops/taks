#!/usr/bin/env python3
"""Add the MVP to an existing orchestrator without replacing drifted code.

Copies only the new tool module and makes exact, idempotent source additions.
Run through the authorized deployment path, then restart both orchestrator
services. Config, credentials and other code are preserved.
"""
from pathlib import Path
import argparse
import shutil

NAMES = {"simulation_read", "simulation_control", "list_reference_docs", "search_reference_docs",
         "search_reference_docs_semantic", "get_reference_doc_context", "list_reference_doc_sections",
         "get_reference_section"}


def prepare(business, bridge):
    marker = "def register_taks_tools(mcp, api_call=call):\n"
    hook = "    from taks_mcp.simulation import register_simulation_tools\n    register_simulation_tools(mcp, api_call)\n"
    if "register_simulation_tools(mcp, api_call)" not in business:
        if business.count(marker) != 1:
            raise ValueError("Unexpected Business MCP registration source")
        business = business.replace(marker, marker + hook, 1)
    # Cached client tool catalogs can use the existing generic service tools.
    original = 'if service not in ("ldap", "mumble", "openfire"):'
    if original in business:
        business = business.replace(original, 'if service not in ("ldap", "mumble", "openfire", "simulation", "reference_docs"):')
    if "safe_business.update(" not in bridge:
        marker = '        allowed = safe_devops if domain == "devops" else safe_business\n'
        if bridge.count(marker) != 1:
            raise ValueError("Unexpected deployed node bridge allowlist source")
        hook = "        safe_business.update(" + repr(NAMES) + ")\n"
        bridge = bridge.replace(marker, hook + marker, 1)
    compile(business, "business.py", "exec")
    compile(bridge, "node_mcp_v2.py", "exec")
    return business, bridge


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--runtime", default="/opt/tak-orch/orchestrator")
    p.add_argument("--source-root", default="/opt/taks")
    a = p.parse_args()
    root, source = Path(a.runtime), Path(a.source_root)
    business, bridge = root/"taks_mcp/business.py", root/"orchestrator_api/node_mcp_v2.py"
    b, n = prepare(business.read_text(), bridge.read_text())
    for path, text in ((business,b),(bridge,n)):
        backup = path.with_suffix(path.suffix + ".pre-simulation")
        if not backup.exists():
            shutil.copy2(path,backup)
        path.write_text(text)
    shutil.copy2(source/"orchestrator/taks_mcp/simulation.py",root/"taks_mcp/simulation.py")


if __name__ == "__main__":
    main()
