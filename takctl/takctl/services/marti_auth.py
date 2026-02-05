from __future__ import annotations
from pathlib import Path

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


# ------------------------------------------------------------
# Option C auth: validate against Marti UserAuthenticationFile.xml
# ------------------------------------------------------------
import os
import xml.etree.ElementTree as ET

_MARTI_NS = {"m": "http://bbn.com/marti/xml/bindings"}

def _bcrypt_or_crypt_check(password: str, hashed: str) -> bool:
    """
    Verify bcrypt hashes from Marti user file.
    Prefers python 'bcrypt' if available; falls back to stdlib 'crypt' if supported.
    """
    pw = password.encode("utf-8")
    h = hashed.encode("utf-8")

    # 1) Preferred: bcrypt module
    try:
        import bcrypt  # type: ignore
        return bool(bcrypt.checkpw(pw, h))
    except Exception:
        pass

    # 2) Fallback: crypt (depends on system libcrypt support for $2a/$2b)
    try:
        import crypt  # type: ignore
        return crypt.crypt(password, hashed) == hashed
    except Exception:
        return False

def check_userauthfile(
    username: str,
    password: str,
    *,
    path: str = "/opt/tak/UserAuthenticationFile.xml",
) -> MartiAuthResult:
    """
    Validate username/password against Marti's UserAuthenticationFile.xml.

    Supported:
      - passwordHashed="true" with bcrypt hashes ($2a$ / $2b$)
      - passwordHashed="false" plaintext password in 'password' attribute

    Returns MartiAuthResult(ok=..., error=...)
    """
    try:
        if not os.path.exists(path):
            return MartiAuthResult(ok=False, status=None, error=f"User file missing: {path}")

        xml = Path(path).read_text(encoding="utf-8")
        root = ET.fromstring(xml)

        # Find matching <User identifier="...">
        users = root.findall("m:User", _MARTI_NS) or root.findall("User")  # tolerate missing ns
        for u in users:
            ident = u.attrib.get("identifier", "")
            if ident != username:
                continue

            # Some users may be cert-only (no password attr)
            stored = u.attrib.get("password")
            if stored is None:
                return MartiAuthResult(ok=False, status=None, error="User has no password attribute")

            hashed_flag = (u.attrib.get("passwordHashed", "true").lower() == "true")

            if not hashed_flag:
                # plaintext compare
                return MartiAuthResult(ok=(password == stored), status=200 if password == stored else 401)

            # hashed compare (bcrypt)
            ok = _bcrypt_or_crypt_check(password, stored)
            return MartiAuthResult(ok=ok, status=200 if ok else 401)

        return MartiAuthResult(ok=False, status=404, error="User not found")

    except Exception as e:
        return MartiAuthResult(ok=False, status=None, error=str(e))
