"""Shared TAKS administrative Marti client: LDAP-backed OAuth, no XML password copy."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import requests
from takctl.config import load_config, load_secrets


@dataclass
class _TokenCache:
    access_token: str = ""
    token_type: str = "Bearer"
    expires_at_epoch: float = 0.0


_TOKEN_CACHE = _TokenCache()
_TOKEN_LOCK = threading.RLock()


def _now() -> float:
    return time.time()


def _token_valid(tok: _TokenCache) -> bool:
    return bool(tok.access_token and tok.expires_at_epoch > _now() + 30)


def _base_url() -> str:
    cfg = load_config()
    base = str(cfg.get("marti_api_base", "https://127.0.0.1:8446") or "").strip().rstrip("/")
    parts = urlsplit(base)
    # The installed web certificate is issued to the node FQDN, not loopback.
    if parts.hostname in ("127.0.0.1", "localhost"):
        fqdn = str(cfg.get("fqdn", "") or "").strip()
        if not fqdn or any(c in fqdn for c in '/:@?#'):
            raise RuntimeError("Node FQDN required for verified Marti TLS")
        base = urlunsplit(("https", fqdn + ":" + str(parts.port or 8446), parts.path, "", ""))
        parts = urlsplit(base)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
        raise RuntimeError("Marti base must be an HTTPS origin")
    return base


def _credentials() -> tuple[str, str]:
    cfg, sec = load_config(), load_secrets()
    user = str(cfg.get("takctl_admin_user", "admin") or "admin").strip()
    pw = str(sec.get("takctl_admin_password", "") or "").strip()
    if not user or not pw:
        raise RuntimeError("Installer TAK admin credential unavailable")
    return user, pw


def _fetch_token() -> _TokenCache:
    user, pw = _credentials()
    response = requests.post(_base_url() + "/oauth/token",
        data={"grant_type": "password", "username": user, "password": pw},
        timeout=20, verify=True, allow_redirects=False)
    if response.status_code != 200:
        raise RuntimeError(f"Marti OAuth login failed: HTTP {response.status_code}")
    try:
        data = response.json()
        token = str(data.get("access_token") or "").strip()
        expires = int(data.get("expires_in", 0))
        if not token or data.get("token_type", "Bearer").lower() != "bearer" or expires <= 0:
            raise ValueError("Invalid token metadata")
    except (ValueError, TypeError, AttributeError):
        raise RuntimeError("Invalid Marti OAuth response") from None
    return _TokenCache(token, "Bearer", _now() + expires)


def get_access_token(force_refresh: bool = False) -> str:
    global _TOKEN_CACHE
    with _TOKEN_LOCK:
        if force_refresh or not _token_valid(_TOKEN_CACHE):
            _TOKEN_CACHE = _fetch_token()
        return _TOKEN_CACHE.access_token


def get_auth_header(force_refresh: bool = False) -> dict[str, str]:
    return {"Authorization": "Bearer " + get_access_token(force_refresh)}


def marti_request(method: str, path: str, *, json_body=None, timeout: int = 20,
                  force_refresh: bool = False) -> requests.Response:
    if not isinstance(path, str) or not path.startswith('/') or path.startswith('//') or '..' in path or '#' in path:
        raise ValueError("Invalid Marti request path")
    url = _base_url() + path
    response = requests.request(method.upper(), url, headers={**get_auth_header(force_refresh),
        "Accept": "application/json"}, json=json_body, timeout=timeout,
        verify=True, allow_redirects=False)
    if response.status_code == 401 and not force_refresh:
        response = requests.request(method.upper(), url, headers={**get_auth_header(True),
            "Accept": "application/json"}, json=json_body, timeout=timeout,
            verify=True, allow_redirects=False)
    return response


def marti_get(path: str, *, force_refresh: bool = False, timeout: int = 20) -> requests.Response:
    return marti_request("GET", path, force_refresh=force_refresh, timeout=timeout)


def marti_json(path: str, *, force_refresh: bool = False, timeout: int = 20) -> Any:
    response = marti_get(path, force_refresh=force_refresh, timeout=timeout)
    if not 200 <= response.status_code < 300:
        raise RuntimeError(f"Marti request failed: HTTP {response.status_code}")
    return response.json()
