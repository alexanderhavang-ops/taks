from __future__ import annotations

import re
import subprocess
from email.message import EmailMessage

from takctl.config import load_config


def _sendmail_path() -> str:
    for p in (
        "/usr/sbin/sendmail",
        "/usr/lib/sendmail",
        "/usr/bin/sendmail",
    ):
        try:
            from pathlib import Path
            if Path(p).exists():
                return p
        except Exception:
            pass
    raise RuntimeError("sendmail not found (/usr/sbin/sendmail, /usr/lib/sendmail, /usr/bin/sendmail)")


def is_valid_email(addr: str) -> bool:
    s = (addr or "").strip()
    if not s:
        return False
    if len(s) > 254:
        return False
    return re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", s) is not None


def _from_addr() -> str:
    cfg = load_config()
    v = (cfg.onboarding_from_addr or "").strip()
    if not v:
        raise RuntimeError("onboarding_from_addr is empty in takctl.conf")
    return v


def _subject(username: str) -> str:
    return f"TAKS onboarding link for {username}"


def _text_body(*, username: str, card_url: str) -> str:
    return (
        f"Hello,\n\n"
        f"Your TAKS onboarding card is ready for user '{username}'.\n\n"
        f"Open this link:\n"
        f"{card_url}\n\n"
        f"The link may expire, so use it promptly.\n\n"
        f"/TAKS\n"
    )


def send_onboarding_email(*, to_addr: str, username: str, card_url: str) -> dict:
    to_addr = (to_addr or "").strip()
    username = (username or "").strip()
    card_url = (card_url or "").strip()

    if not is_valid_email(to_addr):
        raise RuntimeError(f"invalid email address: {to_addr!r}")
    if not username:
        raise RuntimeError("username required for onboarding email")
    if not card_url:
        raise RuntimeError("card_url required for onboarding email")

    msg = EmailMessage()
    msg["From"] = _from_addr()
    msg["To"] = to_addr
    msg["Subject"] = _subject(username)
    msg.set_content(_text_body(username=username, card_url=card_url))

    sendmail = _sendmail_path()
    try:
        proc = subprocess.run(
            [sendmail, "-t", "-oi"],
            input=msg.as_bytes(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except Exception as e:
        raise RuntimeError(f"sendmail exec failed: {e}")

    if proc.returncode != 0:
        err = (proc.stderr or b"").decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"sendmail failed (rc={proc.returncode}): {err[:400]}")

    return {
        "ok": True,
        "to": to_addr,
        "subject": str(msg["Subject"] or ""),
        "delivery": "sendmail",
    }
