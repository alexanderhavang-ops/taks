"""Minimal, expiring bootstrap bearer tokens for bundle downloads.

Tokens are passed via HTTPS headers in EC2 user data. Only SHA-256 token
digests are stored on the orchestrator; no token is placed in the bundle.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import time
from pathlib import Path

from orchestrator_core.bundles import rendered_bundles_dir

TTL_SECONDS = 6 * 3600
NAME = re.compile(r"^[A-Za-z0-9_.-]+\.tar\.gz$")


def _directory() -> Path:
    p = rendered_bundles_dir() / ".bootstrap-auth"
    p.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(p, 0o700)
    return p


def issue(bundle_name: str) -> str:
    if not NAME.fullmatch(bundle_name):
        raise ValueError("invalid bundle name")
    token = secrets.token_urlsafe(32)
    digest = hashlib.sha256(token.encode("ascii")).hexdigest()
    path = _directory() / digest
    data = {"bundle": bundle_name, "expires": int(time.time()) + TTL_SECONDS}
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="ascii") as stream:
        json.dump(data, stream)
    return token


def authorized(bundle_name: str, supplied: str) -> bool:
    if not NAME.fullmatch(bundle_name) or not supplied or len(supplied) > 128:
        return False
    try:
        digest = hashlib.sha256(supplied.encode("ascii")).hexdigest()
        path = _directory() / digest
        data = json.loads(path.read_text(encoding="ascii"))
        return (hmac.compare_digest(str(data.get("bundle", "")), bundle_name)
                and int(data.get("expires", 0)) >= int(time.time()))
    except (OSError, ValueError, UnicodeError, TypeError):
        return False
