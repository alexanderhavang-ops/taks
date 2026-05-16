from __future__ import annotations

import base64
import os
import ssl
import subprocess
import tempfile
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
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
            return MartiAuthResult(ok=True, status=getattr(resp, "status", None))
    except urllib.error.HTTPError as e:
        return MartiAuthResult(ok=False, status=getattr(e, "code", None), error=str(e))
    except Exception as e:
        return MartiAuthResult(ok=False, status=None, error=str(e))


_MARTI_NS = {"m": "http://bbn.com/marti/xml/bindings"}


def _bcrypt_or_crypt_check(password: str, hashed: str) -> bool:
    pw = password.encode("utf-8")
    h = hashed.encode("utf-8")

    try:
        import bcrypt  # type: ignore
        return bool(bcrypt.checkpw(pw, h))
    except Exception:
        pass

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
    Used only when backing_user_store=userauthfile.
    """
    try:
        if not os.path.exists(path):
            return MartiAuthResult(ok=False, status=None, error=f"User file missing: {path}")

        xml = Path(path).read_text(encoding="utf-8")
        root = ET.fromstring(xml)

        users = root.findall("m:User", _MARTI_NS) or root.findall("User")
        for u in users:
            ident = u.attrib.get("identifier", "")
            if ident != username:
                continue

            stored = u.attrib.get("password")
            if stored is None:
                return MartiAuthResult(ok=False, status=None, error="User has no password attribute")

            hashed_flag = (u.attrib.get("passwordHashed", "true").lower() == "true")

            if not hashed_flag:
                ok = password == stored
                return MartiAuthResult(ok=ok, status=200 if ok else 401)

            ok = _bcrypt_or_crypt_check(password, stored)
            return MartiAuthResult(ok=ok, status=200 if ok else 401)

        return MartiAuthResult(ok=False, status=404, error="User not found")

    except Exception as e:
        return MartiAuthResult(ok=False, status=None, error=str(e))


def check_ldap_bind(
    username: str,
    password: str,
    *,
    timeout_s: int = 4,
) -> MartiAuthResult:
    """
    Validate username/password against LDAP by binding as the expected user DN.
    The password is passed via a temporary file so it does not appear in argv.
    """
    if not username or not password:
        return MartiAuthResult(ok=False, status=400, error="username and password required")

    try:
        from takctl.services.ldap_user_store import load_ldap_config

        cfg = load_ldap_config()
        user_dn = cfg.user_dn(username)
    except Exception as e:
        return MartiAuthResult(ok=False, status=None, error=f"LDAP config error: {e}")

    pw_path = None
    try:
        fd, pw_path = tempfile.mkstemp(prefix="takctl-ldap-bind-", text=True)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(password)
        except Exception:
            try:
                os.close(fd)
            except Exception:
                pass
            raise

        cp = subprocess.run(
            ["ldapwhoami", "-x", "-H", cfg.uri, "-D", user_dn, "-y", pw_path],
            text=True,
            capture_output=True,
            timeout=timeout_s,
        )

        if cp.returncode == 0:
            return MartiAuthResult(ok=True, status=200)

        msg = (cp.stderr or cp.stdout or f"ldapwhoami exited {cp.returncode}").strip()
        return MartiAuthResult(ok=False, status=401, error=msg)

    except subprocess.TimeoutExpired:
        return MartiAuthResult(ok=False, status=None, error="LDAP bind timed out")
    except FileNotFoundError:
        return MartiAuthResult(ok=False, status=None, error="ldapwhoami not found")
    except Exception as e:
        return MartiAuthResult(ok=False, status=None, error=str(e))
    finally:
        if pw_path:
            try:
                os.unlink(pw_path)
            except Exception:
                pass


def check_selected_user_store(username: str, password: str) -> MartiAuthResult:
    """
    Validate TAKCTL web login using the configured backing user store.
    """
    try:
        from takctl.services.ldap_user_store import selected_backing_user_store

        store = selected_backing_user_store()
    except Exception as e:
        return MartiAuthResult(ok=False, status=None, error=f"Could not determine backing_user_store: {e}")

    if store == "ldap":
        return check_ldap_bind(username, password)

    return check_userauthfile(username, password)
