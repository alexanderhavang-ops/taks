from __future__ import annotations

import hmac
import json
import os
import time
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, Request

RUNTIME_DIR = Path("/opt/tak/tools/takctl")
SECRET_FILE = RUNTIME_DIR / "secrets" / "session.key"
COOKIE_NAME = "takctl_session"
SESSION_TTL = 8 * 3600  # 8 hours


def _load_secret() -> bytes:
    if SECRET_FILE.exists():
        return SECRET_FILE.read_bytes()
    SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
    key = os.urandom(32)
    SECRET_FILE.write_bytes(key)
    os.chmod(SECRET_FILE, 0o600)
    return key


_SECRET = _load_secret()


def sign_session(payload: dict) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    sig = hmac.new(_SECRET, raw, "sha256").hexdigest()
    return raw.decode() + "." + sig


def unsign_session(token: str) -> Optional[dict]:
    try:
        raw, sig = token.rsplit(".", 1)
        expect = hmac.new(_SECRET, raw.encode(), "sha256").hexdigest()
        if not hmac.compare_digest(sig, expect):
            return None
        return json.loads(raw)
    except Exception:
        return None


def get_session(req: Request) -> Optional[dict]:
    token = req.cookies.get(COOKIE_NAME)
    if not token:
        return None
    sess = unsign_session(token)
    if not sess:
        return None
    exp = sess.get("exp", 0)
    if not isinstance(exp, (int, float)) or time.time() > float(exp):
        return None
    return sess


def require_session(req: Request) -> dict:
    sess = get_session(req)
    if not sess:
        raise HTTPException(status_code=401, detail="not authenticated")
    return sess
