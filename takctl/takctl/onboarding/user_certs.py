from __future__ import annotations

import subprocess
from pathlib import Path


def user_cert_pem_path(username: str) -> Path:
    u = (username or "").strip()
    return Path("/opt/tak/certs/files/04_USERS") / u / f"{u}.pem"


def ensure_user_cert(username: str) -> Path | None:
    """Ensure TAK client cert material exists for an onboarding user.

    The takctl-makecert helper is responsible for producing the structured
    layout expected by package generation:

      /opt/tak/certs/files/04_USERS/<username>/<username>.key
      /opt/tak/certs/files/04_USERS/<username>/<username>.pem
      /opt/tak/certs/files/04_USERS/<username>/<username>.p12
      /opt/tak/certs/files/04_USERS/<username>/.client-password
    """
    u = (username or "").strip()
    if not u:
        return None

    cert_pem = user_cert_pem_path(u)
    if cert_pem.exists():
        return cert_pem

    helper = "/opt/tak/tools/takctl/bin/takctl-makecert"
    p = subprocess.run(
        ["sudo", "-n", helper, "client", u],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    out = (p.stdout or "").strip()
    if p.returncode != 0:
        raise RuntimeError(out or f"failed to create cert for {u}")

    if not cert_pem.exists():
        raise RuntimeError(f"cert helper succeeded but PEM missing: {cert_pem}")

    return cert_pem
