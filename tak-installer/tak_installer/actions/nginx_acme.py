from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from tak_installer.util import sha256_path, diff_text

from tak_installer.runtime_state import get_fqdn


@dataclass(frozen=True)
class NginxAcmeSite:
    template: Path
    dst: Path

    def _fqdn(self, ctx) -> str:
        for key in ("FQDN", "TAKS_FQDN", "TAKS_NODE_FQDN"):
            v = str((ctx.env or {}).get(key) or "").strip()
            if v:
                return v
        return get_fqdn(ctx)

    def inspect(self, ctx) -> dict[str, str]:
        fqdn = self._fqdn(ctx)
        out: dict[str, str] = {}

        if not self.template.is_file():
            out["status"] = "missing-template"
            out["template"] = str(self.template)
            return out

        rendered = self.template.read_text(encoding="utf-8").replace("__FQDN__", fqdn)

        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".conf") as tf:
            tf.write(rendered)
            tmp = Path(tf.name)

        try:
            out["desired_sha256"] = sha256_path(tmp)
            out["dst"] = str(self.dst)

            if self.dst.exists():
                out["dst_sha256"] = sha256_path(self.dst)
                if out["dst_sha256"] == out["desired_sha256"]:
                    out["status"] = "up-to-date"
                else:
                    out["status"] = "differs"
                    out["diff"] = diff_text(self.dst, tmp)
            else:
                out["status"] = "not-installed"
        finally:
            try:
                tmp.unlink()
            except FileNotFoundError:
                pass

        return out
