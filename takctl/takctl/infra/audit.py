from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from takctl.config import RuntimeConfig
from takctl.infra.time import utcnow


@dataclass
class Audit:
    cfg: RuntimeConfig

    def log(self, event: str, detail: str = "") -> None:
        """
        Minimal append-only audit log (safe for CLI + future web).
        """
        p = Path(self.cfg.audit_log)
        p.parent.mkdir(parents=True, exist_ok=True)
        ts = utcnow().isoformat()
        line = f"{ts}\t{event}\t{detail}\n"
        with p.open("a", encoding="utf-8") as f:
            f.write(line)
