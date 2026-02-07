from __future__ import annotations

from pathlib import Path
from tak_installer.util import log


ENV_DIR = Path("/opt/tak/etc")
ENV_FILE = ENV_DIR / "taks.env"


def apply(ctx) -> None:
    """
    Ensure runtime env/state file exists and optionally persist FQDN.

    If FQDN/TAKS_FQDN is provided via env during apply, we persist it into:
      /opt/tak/etc/taks.env

    If not provided, we do NOT overwrite existing file.
    """
    ENV_DIR.mkdir(parents=True, exist_ok=True)

    fqdn = (ctx.env.get("FQDN") or ctx.env.get("TAKS_FQDN") or "").strip()

    if fqdn:
        content = (
            "# Managed by tak-installer\n"
            f"TAKS_FQDN={fqdn}\n"
        )
        ENV_FILE.write_text(content, encoding="utf-8")
        ENV_FILE.chmod(0o644)
        log.info(f"taks-env: wrote {ENV_FILE} (TAKS_FQDN={fqdn})")
    else:
        if ENV_FILE.exists():
            log.info(f"taks-env: {ENV_FILE} already exists (no env override)")
        else:
            log.info(f"taks-env: {ENV_FILE} not present and no FQDN provided (will require it later)")


class _Action:
    ID = "taks-env"

    def inspect(self, ctx) -> int:
        print(f"Inspecting {self.ID} action...")
        return 0 if ENV_FILE.exists() else 1

    def apply(self, ctx) -> int:
        print(f"Applying {self.ID} action...")
        apply(ctx)
        return 0


ACTION = _Action()

