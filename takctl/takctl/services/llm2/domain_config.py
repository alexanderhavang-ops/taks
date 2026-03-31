from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

INFRA_DIR_DEFAULT = Path("/opt/tak/tools/takctl/llm-infra")


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def infra_domains_root(infra_dir: Path | None = None) -> Path:
    base = Path(infra_dir) if infra_dir else INFRA_DIR_DEFAULT
    return base / "domains"


def load_domain_config(infra_dir: Path, domain: str) -> Dict[str, Any]:
    p = infra_domains_root(infra_dir) / domain / "config.json"
    if not p.exists():
        raise RuntimeError(f"missing domain config: {p}")
    obj = _read_json(p)
    if not isinstance(obj, dict):
        raise RuntimeError(f"invalid domain config object: {p}")
    return obj


def discover_enabled_domains(infra_dir: Path) -> List[str]:
    root = infra_domains_root(infra_dir)
    if not root.exists():
        return []

    out: List[str] = []
    for p in sorted(root.iterdir(), key=lambda x: x.name):
        if not p.is_dir():
            continue
        cfgp = p / "config.json"
        if not cfgp.exists():
            continue
        try:
            cfg = _read_json(cfgp)
        except Exception:
            continue
        if cfg.get("enabled", True) is False:
            continue
        out.append(p.name)

    if "summary" in out:
        out = ["summary"] + [d for d in out if d != "summary"]
    return out


def phase_enabled(cfg: Dict[str, Any], phase: str) -> bool:
    phases = cfg.get("phases") or {}
    pobj = phases.get(phase) or {}
    if not isinstance(pobj, dict):
        return False
    return pobj.get("enabled", True) is not False


def domain_mode(cfg: Dict[str, Any]) -> str:
    return str(cfg.get("mode") or "leaf").strip().lower()


def phase_input(cfg: Dict[str, Any], phase: str) -> str:
    phases = cfg.get("phases") or {}
    pobj = phases.get(phase) or {}
    if not isinstance(pobj, dict):
        return ""
    return str(pobj.get("input") or "").strip()


def upstream_domains(cfg: Dict[str, Any]) -> List[str]:
    phases = cfg.get("phases") or {}
    p2 = phases.get("phase2") or {}
    vals = p2.get("upstream_domains") or []
    if not isinstance(vals, list):
        return []
    return [str(x).strip() for x in vals if str(x).strip()]


def phase_output_schema(cfg: Dict[str, Any], phase: str) -> str:
    phases = cfg.get("phases") or {}
    pobj = phases.get(phase) or {}
    if not isinstance(pobj, dict):
        return ""
    return str(pobj.get("output_schema") or "").strip()
