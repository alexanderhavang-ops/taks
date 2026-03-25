from __future__ import annotations

import os
import secrets
import subprocess
from pathlib import Path

from tak_installer.util import log


SECRETS_CONF = Path("/opt/tak/tools/takctl/secrets.conf")
HELPER = Path("/opt/tak/tools/takctl/bin/takctl-usermgr")

DEFAULT_USERNAME = "taks-api"


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


def _parse_env(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("[") and line.endswith("]"):
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def _write_atomic(path: Path, data: str, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(data, encoding="utf-8")
    os.chmod(tmp, mode)
    tmp.replace(path)


def _run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=check)


def _load_runtime_secrets() -> dict[str, str]:
    if not SECRETS_CONF.exists():
        return {}
    return _parse_env(SECRETS_CONF.read_text(encoding="utf-8"))


def _write_runtime_secrets(existing: dict[str, str]) -> None:
    existing.setdefault("db_password", "")
    existing.setdefault("ca_signing_p12_pass", "")
    existing.setdefault("user_key_pass", "")
    existing.setdefault("onboarding_client_p12_default_pass", "")
    existing.setdefault("marti_api_username", DEFAULT_USERNAME)
    existing.setdefault("marti_api_password", "")
    existing.setdefault("bedrock_api_key", "")

    content = (
        "[takctl-secrets]\n"
        f"db_password = {existing.get('db_password', '')}\n"
        f"ca_signing_p12_pass = {existing.get('ca_signing_p12_pass', '')}\n"
        f"user_key_pass = {existing.get('user_key_pass', '')}\n"
        f"onboarding_client_p12_default_pass = {existing.get('onboarding_client_p12_default_pass', '')}\n"
        f"marti_api_username = {existing.get('marti_api_username', '')}\n"
        f"marti_api_password = {existing.get('marti_api_password', '')}\n"
        f"bedrock_api_key = {existing.get('bedrock_api_key', '')}\n"
    )

    _write_atomic(SECRETS_CONF, content, 0o640)
    _run(["chown", "tak:tak", str(SECRETS_CONF)], check=False)
    log.info("takctl-marti-api-user: ensured %s", SECRETS_CONF)


def _ensure_secret_values() -> tuple[str, str]:
    sec = _load_runtime_secrets()

    user = (sec.get("marti_api_username") or "").strip()
    if not user:
        user = DEFAULT_USERNAME
        sec["marti_api_username"] = user

    pw = (sec.get("marti_api_password") or "").strip()
    if not pw:
        pw = _gen_strong_password(20)
        sec["marti_api_password"] = pw

    _write_runtime_secrets(sec)
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
        log.info("  secrets: %s", SECRETS_CONF)
        log.info("  helper: %s", HELPER)
        log.info("  default marti_api_username: %s", DEFAULT_USERNAME)
        return 0

    def apply(self, ctx) -> int:
        log.info("Applying %s action...", self.ID)
        apply(ctx)
        return 0


ACTION = _Action()
