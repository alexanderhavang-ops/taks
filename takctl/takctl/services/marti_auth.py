from __future__ import annotations

import base64
import ssl
import urllib.request
from dataclasses import dataclass
from typing import Optional


@dataclass
class MartiAuthResult:
    ok: bool
    status: Optional[int] = None
    error: str = ""


def check_basic_auth(
    username: str,
    password: str,
    *,
    url: str = "https://127.0.0.1:8443/Marti/api/version",
    verify_tls: bool = False,
    timeout_s: int = 4,
) -> MartiAuthResult:
    """
    Validate username/password by attempting a protected Marti endpoint using HTTP Basic auth.

    - url: choose an endpoint that requires auth (version often does)
    - verify_tls=False for now (local loopback). Later we can wire to TAK CA bundle.
    """
    userpass = f"{username}:{password}".encode("utf-8")
    auth = base64.b64encode(userpass).decode("ascii")

    req = urllib.request.Request(url, method="GET")
    req.add_header("Authorization", f"Basic {auth}")

    ctx = None
    if not verify_tls:
        ctx = ssl._create_unverified_context()

    try:
        with urllib.request.urlopen(req, timeout=timeout_s, context=ctx) as resp:
            # If we get here, auth succeeded
            return MartiAuthResult(ok=True, status=getattr(resp, "status", None))
    except urllib.error.HTTPError as e:
        # 401/403 expected for bad creds; other codes indicate config/endpoint mismatch
        return MartiAuthResult(ok=False, status=getattr(e, "code", None), error=str(e))
    except Exception as e:
        return MartiAuthResult(ok=False, status=None, error=str(e))
