from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Optional

import requests

from takctl.config import load_config, load_secrets


@dataclass
class _TokenCache:
    access_token: str = ""
    token_type: str = "Bearer"
    expires_at_epoch: float = 0.0


_TOKEN_CACHE = _TokenCache()


def _now() -> float:
    return time.time()


def _token_valid(tok: _TokenCache) -> bool:
    if not tok.access_token:
        return False
    # refresh a little early
    return tok.expires_at_epoch > (_now() + 30.0)


def _base_url() -> str:
    cfg = load_config()
    base = (cfg.marti_api_base or "").strip().rstrip("/")
    if not base:
        raise RuntimeError("marti_api_base is empty in takctl.conf")
    return base


def _credentials() -> tuple[str, str]:
    sec = load_secrets()
    user = (sec.marti_api_username or "").strip()
    pw = (sec.marti_api_password or "").strip()
    if not user:
        raise RuntimeError("marti_api_username is empty in secrets.conf")
    if not pw:
        raise RuntimeError("marti_api_password is empty in secrets.conf")
    return user, pw


def _fetch_token() -> _TokenCache:
    base = _base_url()
    user, pw = _credentials()

    r = requests.post(
        f"{base}/oauth/token",
        files={
            "grant_type": (None, "password"),
            "username": (None, user),
            "password": (None, pw),
        },
        timeout=20,
        verify=False,
    )
    txt = r.text[:400]
    if not r.ok:
        raise RuntimeError(f"Marti token fetch failed: HTTP {r.status_code}: {txt}")

    j = r.json()
    token = str(j.get("access_token") or "").strip()
    token_type = str(j.get("token_type") or "Bearer").strip() or "Bearer"
    expires_in = int(j.get("expires_in") or 0)

    if not token:
        raise RuntimeError("Marti token fetch returned no access_token")

    return _TokenCache(
        access_token=token,
        token_type=token_type,
        expires_at_epoch=_now() + max(expires_in, 60),
    )


def get_access_token(force_refresh: bool = False) -> str:
    global _TOKEN_CACHE
    if force_refresh or not _token_valid(_TOKEN_CACHE):
        _TOKEN_CACHE = _fetch_token()
    return _TOKEN_CACHE.access_token


def get_auth_header(force_refresh: bool = False) -> dict[str, str]:
    global _TOKEN_CACHE
    if force_refresh or not _token_valid(_TOKEN_CACHE):
        _TOKEN_CACHE = _fetch_token()
    return {"Authorization": f"{_TOKEN_CACHE.token_type} {_TOKEN_CACHE.access_token}"}


def marti_get(path: str, *, force_refresh: bool = False, timeout: int = 20) -> requests.Response:
    base = _base_url()
    p = "/" + str(path or "").lstrip("/")
    hdr = get_auth_header(force_refresh=force_refresh)

    r = requests.get(
        f"{base}{p}",
        headers=hdr,
        timeout=timeout,
        verify=False,
    )

    if r.status_code in (401, 403) and not force_refresh:
        hdr = get_auth_header(force_refresh=True)
        r = requests.get(
            f"{base}{p}",
            headers=hdr,
            timeout=timeout,
            verify=False,
        )

    return r


def marti_json(path: str, *, force_refresh: bool = False, timeout: int = 20) -> Any:
    r = marti_get(path, force_refresh=force_refresh, timeout=timeout)
    txt = r.text[:400]
    if not r.ok:
        raise RuntimeError(f"Marti GET {path} failed: HTTP {r.status_code}: {txt}")
    return r.json()
