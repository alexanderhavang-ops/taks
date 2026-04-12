from __future__ import annotations

from typing import Any, Dict

from orchestrator_core.unit_bootstrap import effective_kv_by_file


def _flatten_component_values(data: Dict[str, Any]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not isinstance(data, dict):
        return out

    for _name, obj in data.items():
        if isinstance(obj, dict):
            for k, v in obj.items():
                ks = str(k).strip()
                if ks:
                    out[ks] = str(v).strip()
            continue

        text = str(obj or "")
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or line.startswith("[") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            ks = k.strip()
            if ks:
                out[ks] = v.strip()

    return out


def capabilities_for_policy(policy_id: str) -> Dict[str, bool]:
    pid = str(policy_id or "").strip().lower()
    return {
        # replay/simulate is military-only for now
        "replay": pid == "hemvarnet",
    }


def describe_unit_policy(unit_path: str) -> Dict[str, Any]:
    conf_d = effective_kv_by_file(unit_path, secret=False)
    conf_vals = _flatten_component_values(conf_d)

    policy_id = str(conf_vals.get("default_policy_id") or "").strip()

    return {
        "id": policy_id or None,
        "capabilities": capabilities_for_policy(policy_id),
    }
