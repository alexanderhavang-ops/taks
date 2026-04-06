from __future__ import annotations

from pathlib import Path


TAKS_ENV = Path("/opt/tak/etc/taks.env")
BOOTSTRAP_NODE_ENV = Path("/etc/taks-bootstrap.d/node.env")
NODE_ENV = Path("/etc/taks/node.env")


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


def _parse_env_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    return _parse_env_text(path.read_text(encoding="utf-8"))


def get_fqdn(ctx) -> str:
    """
    Canonical FQDN resolution:
      1) ctx/env: FQDN, TAKS_FQDN, TAKS_NODE_FQDN
      2) bootstrap env: /etc/taks-bootstrap.d/node.env
      3) node env: /etc/taks/node.env
      4) runtime state: /opt/tak/etc/taks.env
    """
    env = getattr(ctx, "env", {}) or {}

    for key in ("FQDN", "TAKS_FQDN", "TAKS_NODE_FQDN"):
        fqdn = str(env.get(key) or "").strip()
        if fqdn:
            return fqdn

    for path in (BOOTSTRAP_NODE_ENV, NODE_ENV, TAKS_ENV):
        data = _parse_env_file(path)
        for key in ("FQDN", "TAKS_FQDN", "TAKS_NODE_FQDN"):
            fqdn = str(data.get(key) or "").strip()
            if fqdn:
                return fqdn

    raise RuntimeError(
        "FQDN not set. Checked ctx/env (FQDN, TAKS_FQDN, TAKS_NODE_FQDN), "
        "/etc/taks-bootstrap.d/node.env, /etc/taks/node.env, and /opt/tak/etc/taks.env."
    )
