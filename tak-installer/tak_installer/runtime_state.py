from __future__ import annotations

from pathlib import Path


RUNTIME_CONF_D = Path("/opt/tak/tools/takctl/conf.d")
BOOTSTRAP_CONF_D = Path("/etc/taks-bootstrap.d/config.d")


def _parse_kv_text(s: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in str(s or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k:
            out[k] = v
    return out


def _load_conf_dir(dir_path: Path) -> dict[str, str]:
    if not dir_path.is_dir():
        return {}
    merged: dict[str, str] = {}
    for p in sorted(dir_path.glob("*.conf")):
        if not p.is_file():
            continue
        merged.update(_parse_kv_text(p.read_text(encoding="utf-8")))
    return merged


def get_fqdn(ctx) -> str:
    """
    Canonical FQDN resolution:
      1) runtime conf.d
      2) bootstrap config.d (first-install seed only)
    """
    for dir_path in (RUNTIME_CONF_D, BOOTSTRAP_CONF_D):
        data = _load_conf_dir(dir_path)
        for key in ("fqdn", "node_fqdn", "tak_public_host", "public_host", "hostname"):
            fqdn = str(data.get(key) or "").strip()
            if fqdn:
                return fqdn

    raise RuntimeError(
        "FQDN not set. Checked /opt/tak/tools/takctl/conf.d and /etc/taks-bootstrap.d/config.d."
    )
