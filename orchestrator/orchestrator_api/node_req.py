# orchestrator/orchestrator_api/node_req.py
from __future__ import annotations

import os
from typing import Any, Dict


def normalize_node_req(req: Dict[str, Any]) -> Dict[str, Any]:
    """
    Backward/UX compatible normalization for node requests.

    Accepts (legacy / UI):
      - battalion (old) -> unit_path (new)
      - role may be omitted (defaults to "tak-node")
      - hostname/name/fqdn defaulted if missing

    Returns a dict safe to pass into NodeRequest(**d).
    """
    d = dict(req or {})

    # legacy key
    if "unit_path" not in d and "battalion" in d:
        d["unit_path"] = str(d.pop("battalion"))

    unit_path = str(d.get("unit_path") or "").strip()
    if not unit_path:
        raise ValueError("Missing unit_path")

    # default role
    role = str(d.get("role") or "").strip()
    if not role:
        role = "tak-node"
    d["role"] = role

    # hostname default (DNS-ish)
    hostname = str(d.get("hostname") or "").strip()
    if not hostname:
        safe = unit_path.replace("/", "-").replace("_", "-")
        hostname = f"tak-{safe}" if safe else "tak-node"
    d["hostname"] = hostname

    # AWS Name tag default
    name = str(d.get("name") or "").strip()
    if not name:
        name = hostname
    d["name"] = name

    # fqdn default
    fqdn = str(d.get("fqdn") or "").strip()
    if not fqdn:
        base = (os.environ.get("TAKS_DEFAULT_NODE_DOMAIN") or "tak-hv-sandbox.se").strip()
        if unit_path and "." in unit_path:
            fqdn = unit_path
        else:
            fqdn = f"{unit_path}.{base}"
    d["fqdn"] = fqdn

    return d

