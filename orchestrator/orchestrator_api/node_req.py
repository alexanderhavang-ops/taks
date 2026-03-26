from __future__ import annotations

from typing import Any, Dict
from orchestrator_core.config import load_orch_config


def normalize_node_req(req: Dict[str, Any]) -> Dict[str, Any]:
    """
    Backward/UX compatible normalization for node requests.

    Accepts (legacy / UI):
      - battalion (old) -> unit_path (new)
      - role may be omitted (defaults to "tak-node")
      - hostname/name/fqdn defaulted if missing
      - bare fqdn like "48HVBAT" is canonicalized to "<name>.<default_node_domain>"
    """
    d = dict(req or {})

    if "unit_path" not in d and "battalion" in d:
        d["unit_path"] = str(d.pop("battalion"))

    unit_path = str(d.get("unit_path") or "").strip().lower()
    if not unit_path:
        raise ValueError("Missing unit_path")

    role = str(d.get("role") or "").strip()
    if not role:
        role = "tak-node"
    d["role"] = role

    hostname = str(d.get("hostname") or "").strip()
    if not hostname:
        safe = unit_path.replace("/", "-").replace("_", "-")
        hostname = f"tak-{safe}" if safe else "tak-node"
    d["hostname"] = hostname

    name = str(d.get("name") or "").strip()
    if not name:
        name = hostname
    d["name"] = name

    cfg = load_orch_config()
    dns_suffix = str(cfg.nodes.default_node_domain).strip().strip(".")

    fqdn = str(d.get("fqdn") or "").strip().strip(".").lower()
    if not fqdn:
        fqdn = unit_path
    if "." not in fqdn:
        fqdn = f"{fqdn}.{dns_suffix}"

    d["unit_path"] = unit_path
    d["fqdn"] = fqdn.lower()

    return d
