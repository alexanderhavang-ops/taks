from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


RUNTIME_ROOT = Path("/opt/tak/takctl-state/policies.d")
BUILTIN_ROOT = Path(__file__).resolve().parent / "policies_builtin"


@dataclass
class PolicyRef:
    policy_id: str
    name: str
    version: str
    source: str  # "runtime" | "builtin"
    path: Path
    has_doc: bool


def _load_json(p: Path) -> Dict[str, Any]:
    return json.loads(p.read_text(encoding="utf-8"))


def _pick_dir(policy_id: str) -> Tuple[str, Path]:
    pid = (policy_id or "").strip()
    if not pid:
        raise KeyError("policy_id required")

    rt = RUNTIME_ROOT / pid
    if (rt / "policy.json").exists():
        return ("runtime", rt)

    bt = BUILTIN_ROOT / pid
    if (bt / "policy.json").exists():
        return ("builtin", bt)

    raise KeyError(f"unknown policy: {pid}")


def default_policy_id() -> str:
    return (os.getenv("TAKS_DEFAULT_POLICY_ID") or "hemvarnet").strip() or "hemvarnet"


def list_policies() -> List[PolicyRef]:
    seen: Dict[str, PolicyRef] = {}

    # builtin first
    if BUILTIN_ROOT.exists():
        for d in sorted([x for x in BUILTIN_ROOT.iterdir() if x.is_dir()]):
            pj = d / "policy.json"
            if not pj.exists():
                continue
            j = _load_json(pj)
            pid = str(j.get("id") or d.name).strip()
            seen[pid] = PolicyRef(
                policy_id=pid,
                name=str(j.get("name") or pid),
                version=str(j.get("version") or "0"),
                source="builtin",
                path=d,
                has_doc=(d / "doc.pdf").exists(),
            )

    # runtime overrides win
    if RUNTIME_ROOT.exists():
        for d in sorted([x for x in RUNTIME_ROOT.iterdir() if x.is_dir()]):
            pj = d / "policy.json"
            if not pj.exists():
                continue
            j = _load_json(pj)
            pid = str(j.get("id") or d.name).strip()
            seen[pid] = PolicyRef(
                policy_id=pid,
                name=str(j.get("name") or pid),
                version=str(j.get("version") or "0"),
                source="runtime",
                path=d,
                has_doc=(d / "doc.pdf").exists(),
            )

    return [seen[k] for k in sorted(seen.keys())]


def get_policy(policy_id: str) -> Dict[str, Any]:
    src, d = _pick_dir(policy_id)
    j = _load_json(d / "policy.json")
    j["_meta"] = {
        "policy_id": str(j.get("id") or policy_id),
        "source": src,
        "has_doc": (d / "doc.pdf").exists(),
    }
    return j


def get_doc_path(policy_id: str) -> Optional[Path]:
    try:
        _, d = _pick_dir(policy_id)
    except KeyError:
        return None
    p = d / "doc.pdf"
    return p if p.exists() else None
