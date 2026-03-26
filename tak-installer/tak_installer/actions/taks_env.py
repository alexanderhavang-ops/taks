from __future__ import annotations

from pathlib import Path
from tak_installer.util import log


ENV_DIR = Path("/opt/tak/etc")
ENV_FILE = ENV_DIR / "taks.env"


def _pick(ctx, *keys: str) -> str:
    for k in keys:
        v = (ctx.env.get(k) or "").strip()
        if v:
            return v
    return ""


def apply(ctx) -> None:
    """
    Ensure runtime env/state file exists and persist selected canonical node vars.

    We currently persist:
      - TAKS_FQDN
      - TAKS_NODE_CERT_MODEL
      - LE_EMAIL

    Canonical env priority:
      - FQDN or TAKS_FQDN -> persisted as TAKS_FQDN
      - TAKS_NODE_CERT_MODEL
      - LE_EMAIL

    If none of these are provided, we do NOT overwrite an existing file.
    """
    ENV_DIR.mkdir(parents=True, exist_ok=True)

    fqdn = _pick(ctx, "FQDN", "TAKS_FQDN")
    cert_model = _pick(ctx, "TAKS_NODE_CERT_MODEL")
    le_email = _pick(ctx, "LE_EMAIL")

    rows: list[str] = ["# Managed by tak-installer"]

    if fqdn:
        rows.append(f"TAKS_FQDN={fqdn}")
    if cert_model:
        rows.append(f"TAKS_NODE_CERT_MODEL={cert_model}")
    if le_email:
        rows.append(f"LE_EMAIL={le_email}")

    if len(rows) > 1:
        content = "\n".join(rows) + "\n"
        ENV_FILE.write_text(content, encoding="utf-8")
        ENV_FILE.chmod(0o644)
        log.info(
            f"taks-env: wrote {ENV_FILE} "
            f"(TAKS_FQDN={fqdn or '-'} "
            f"TAKS_NODE_CERT_MODEL={cert_model or '-'} "
            f"LE_EMAIL={'set' if le_email else '-'})"
        )
    else:
        if ENV_FILE.exists():
            log.info(f"taks-env: {ENV_FILE} already exists (no env override)")
        else:
            log.info(f"taks-env: {ENV_FILE} not present and no relevant env provided")


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
