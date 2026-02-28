from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


@dataclass(frozen=True)
class DomainPhaseConfig:
    sql_dir: Optional[str] = None
    prompt_dir: Optional[str] = None


@dataclass(frozen=True)
class DomainConfig:
    domain: str
    enabled: bool
    phase1: DomainPhaseConfig
    phase2: DomainPhaseConfig
    phase3: DomainPhaseConfig
    raw: dict[str, Any]


def load_domain_config(domain_dir: Path) -> DomainConfig:
    cfg_path = domain_dir / "config.json"
    raw = json.loads(cfg_path.read_text(encoding="utf-8"))
    dom = str(raw.get("domain") or domain_dir.name)
    enabled = bool(raw.get("enabled", True))
    phases = raw.get("phases") or {}

    def _p(name: str) -> DomainPhaseConfig:
        p = phases.get(name) or {}
        return DomainPhaseConfig(
            sql_dir=p.get("sql_dir"),
            prompt_dir=p.get("prompt_dir"),
        )

    return DomainConfig(
        domain=dom,
        enabled=enabled,
        phase1=_p("phase1"),
        phase2=_p("phase2"),
        phase3=_p("phase3"),
        raw=raw,
    )
