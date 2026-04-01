from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def infra_domains_root(infra_dir: Path) -> Path:
    return infra_dir / 'domains'


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))


def discover_enabled_domains(infra_dir: Path) -> list[str]:
    root = infra_domains_root(infra_dir)
    out: list[str] = []
    if not root.exists():
        return out
    for p in sorted(root.iterdir(), key=lambda x: x.name):
        if p.name.startswith('_'):
            continue
        if not p.is_dir() or not (p / 'config.json').exists():
            continue
        try:
            cfg = _read_json(p / 'config.json')
        except Exception:
            continue
        if cfg.get('enabled', True) is False:
            continue
        out.append(p.name)
    if 'summary' in out:
        out = ['summary'] + [x for x in out if x != 'summary']
    return out


def load_domain_config(infra_dir: Path, domain: str) -> dict[str, Any]:
    p = infra_domains_root(infra_dir) / domain / 'config.json'
    return _read_json(p)


def phase_enabled(cfg: dict[str, Any], phase: str) -> bool:
    pobj = ((cfg.get('phases') or {}).get(phase) or {})
    return isinstance(pobj, dict) and pobj.get('enabled', True) is not False


def phase_input(cfg: dict[str, Any], phase: str) -> str:
    pobj = ((cfg.get('phases') or {}).get(phase) or {})
    return str(pobj.get('input') or '').strip()


def phase_output_schema(cfg: dict[str, Any], phase: str) -> str:
    pobj = ((cfg.get('phases') or {}).get(phase) or {})
    return str(pobj.get('output_schema') or '').strip()


def upstream_domains(cfg: dict[str, Any]) -> list[str]:
    vals = (((cfg.get('phases') or {}).get('phase2') or {}).get('upstream_domains') or [])
    return [str(x).strip() for x in vals if str(x).strip()]
