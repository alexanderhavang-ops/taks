from __future__ import annotations

import os
import subprocess
from pathlib import Path

from tak_installer.util import log
from takctl.config import load_secrets
from takctl.config_store import save_runtime_secrets_view


HELPER = Path("/opt/tak/tools/takctl/bin/takctl-usermgr")
DEFAULT_USERNAME = "taks-api"
COMPONENT = "marti_api"


def _gen_strong_password(length: int = 20) -> str:
    import secrets as _secrets

    specials = r"-_!@#$%^&*(){}[]+=~`|:;<>,./?"
    uppers = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    lowers = "abcdefghijklmnopqrstuvwxyz"
    digits = "0123456789"

    n = max(int(length), 15)

    chars = [
        _secrets.choice(uppers),
        _secrets.choice(lowers),
        _secrets.choice(digits),
        _secrets.choice(specials),
    ]

    alphabet = uppers + lowers + digits + specials
    while len(chars) < n:
        chars.append(_secrets.choice(alphabet))

    for i in range(len(chars) - 1, 0, -1):
        j = _secrets.randbelow(i + 1)
        chars[i], chars[j] = chars[j], chars[i]

    return "".join(chars)


def _run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=check)


def _component_path() -> Path:
    return Path("/opt/tak/tools/takctl/secrets.d") / f"{COMPONENT}.conf"


def _normalize_component_file() -> None:
    p = _component_path()
    if not p.exists():
        return
    try:
        os.chmod(p, 0o640)
    except Exception:
        pass
    _run(["chown", "tak:tak", str(p)], check=False)


def _ensure_secret_values() -> tuple[str, str]:
    sec = load_secrets()
    changed = False

    user = (sec.get("marti_api_username", "") or "").strip()
    if not user:
        user = DEFAULT_USERNAME
        sec.set("marti_api_username", user, component=COMPONENT)
        changed = True

    pw = (sec.get("marti_api_password", "") or "").strip()
    if not pw:
        pw = _gen_strong_password(20)
        sec.set("marti_api_password", pw, component=COMPONENT)
        changed = True

    if changed:
        save_runtime_secrets_view(sec)
        _normalize_component_file()

    return user, pw


def _bootstrap_user(user: str, pw: str) -> None:
    if not HELPER.exists():
        raise RuntimeError(f"missing helper: {HELPER}")
    if not HELPER.is_file():
        raise RuntimeError(f"helper is not a file: {HELPER}")
    if not os.access(str(HELPER), os.X_OK):
        raise RuntimeError(f"helper not executable: {HELPER}")

    p = subprocess.run(
        [str(HELPER), "usermod", "-A", "-p", pw, user],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    out = (p.stdout or "").strip()
    if p.returncode != 0:
        raise RuntimeError(out or f"failed to ensure marti bootstrap user: {user}")

    log.info("takctl-marti-api-user: ensured Marti bootstrap user %s: %s", user, out)


def apply(ctx) -> None:
    user, pw = _ensure_secret_values()
    _bootstrap_user(user, pw)


class _Action:
    ID = "takctl-marti-api-user"

    def inspect(self, ctx) -> int:
        log.info("Inspecting %s action...", self.ID)
        log.info("  secrets component: %s", _component_path())
        log.info("  helper: %s", HELPER)
        log.info("  default marti_api_username: %s", DEFAULT_USERNAME)
        return 0

    def apply(self, ctx) -> int:
        log.info("Applying %s action...", self.ID)
        apply(ctx)
        return 0


ACTION = _Action()
