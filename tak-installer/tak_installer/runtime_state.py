from __future__ import annotations

from pathlib import Path


TAKS_ENV = Path("/opt/tak/etc/taks.env")


def _parse_env_text(s: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in s.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k:
            out[k] = v
    return out


def get_fqdn(ctx) -> str:
    """
    Canonical FQDN resolution:
      1) env: FQDN or TAKS_FQDN
      2) runtime state: /opt/tak/etc/taks.env (TAKS_FQDN or FQDN)
    """
    fqdn = (ctx.env.get("FQDN") or ctx.env.get("TAKS_FQDN") or "").strip()
    if fqdn:
        return fqdn

    if TAKS_ENV.is_file():
        data = _parse_env_text(TAKS_ENV.read_text(encoding="utf-8"))
        fqdn = (data.get("TAKS_FQDN") or data.get("FQDN") or "").strip()
        if fqdn:
            return fqdn

    raise RuntimeError(
        "FQDN not set. Provide FQDN env var (or TAKS_FQDN), or write /opt/tak/etc/taks.env with TAKS_FQDN=<node-fqdn>."
    )

