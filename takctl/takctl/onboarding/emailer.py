from __future__ import annotations

import json
import re
import subprocess
from email.message import EmailMessage
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from takctl.config import load_config


_RUNTIME_ONBOARDING_SECRET = "/opt/tak/tools/takctl/secrets.d/onboarding.conf"
_DEV_FALLBACK_SECRET = "/opt/taks/secrets.d/mail.conf"


def _sendmail_path() -> str:
    for p in (
        "/usr/sbin/sendmail",
        "/usr/lib/sendmail",
        "/usr/bin/sendmail",
    ):
        if Path(p).exists():
            return p
    raise RuntimeError("sendmail not found (/usr/sbin/sendmail, /usr/lib/sendmail, /usr/bin/sendmail)")


def is_valid_email(addr: str) -> bool:
    s = (addr or "").strip()
    if not s:
        return False
    if len(s) > 254:
        return False
    return re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", s) is not None


def _cfg_get(name: str, default: str = "") -> str:
    cfg = load_config()
    try:
        v = getattr(cfg, name)
    except Exception:
        try:
            v = cfg.get(name, default)
        except Exception:
            v = default
    return str(v or "").strip()


def _provider() -> str:
    v = _cfg_get("onboarding_email_provider", "").lower()
    if v in ("", "sendmail"):
        return "sendmail"
    if v == "resend":
        return "resend"
    raise RuntimeError(f"unsupported onboarding_email_provider: {v!r}")


def _from_addr() -> str:
    v = _cfg_get("onboarding_from_addr", "")
    if not v:
        raise RuntimeError("onboarding_from_addr is empty in takctl config")
    return v


def _reply_to() -> str:
    return _cfg_get("onboarding_reply_to", "")


def _read_kv_file(path: str) -> dict[str, str]:
    out: dict[str, str] = {}
    p = Path(path)
    if not p.exists():
        return out

    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def _resend_api_key() -> str:
    for path in (_RUNTIME_ONBOARDING_SECRET, _DEV_FALLBACK_SECRET):
        kv = _read_kv_file(path)
        key = (kv.get("resend.apikey") or "").strip()
        if key:
            return key
    raise RuntimeError(
        f"resend.apikey missing in {_RUNTIME_ONBOARDING_SECRET}"
        f" (dev fallback also checked: {_DEV_FALLBACK_SECRET})"
    )


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


def _html_body(*, username: str, card_url: str) -> str:
    return (
        "<html><body>"
        "<p>Hello,</p>"
        f"<p>Your TAKS onboarding card is ready for user <b>{username}</b>.</p>"
        f'<p><a href="{card_url}">Open onboarding card</a></p>'
        "<p>The link may expire, so use it promptly.</p>"
        "<p>/TAKS</p>"
        "</body></html>"
    )


def _send_via_sendmail(*, to_addr: str, username: str, card_url: str) -> dict:
    msg = EmailMessage()
    msg["From"] = _from_addr()
    msg["To"] = to_addr
    msg["Subject"] = _subject(username)

    reply_to = _reply_to()
    if reply_to:
        msg["Reply-To"] = reply_to

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


def _send_via_resend(*, to_addr: str, username: str, card_url: str) -> dict:
    payload = {
        "from": _from_addr(),
        "to": [to_addr],
        "subject": _subject(username),
        "text": _text_body(username=username, card_url=card_url),
        "html": _html_body(username=username, card_url=card_url),
    }

    reply_to = _reply_to()
    if reply_to:
        payload["reply_to"] = [reply_to]

    req = Request(
        "https://api.resend.com/emails",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {_resend_api_key()}",
            "Content-Type": "application/json",
            "User-Agent": "taks-onboarding/1.0",
        },
    )

    try:
        with urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except HTTPError as e:
        try:
            err_body = e.read().decode("utf-8", errors="replace")
        except Exception:
            err_body = ""
        raise RuntimeError(f"resend failed (http={e.code}): {err_body[:400]}")
    except URLError as e:
        raise RuntimeError(f"resend connection failed: {e}")
    except Exception as e:
        raise RuntimeError(f"resend send failed: {e}")

    try:
        out = json.loads(raw or "{}")
    except Exception:
        out = {"raw": raw}

    return {
        "ok": True,
        "to": to_addr,
        "subject": _subject(username),
        "delivery": "resend",
        "provider_response": out,
    }


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

    provider = _provider()
    if provider == "sendmail":
        return _send_via_sendmail(to_addr=to_addr, username=username, card_url=card_url)
    if provider == "resend":
        return _send_via_resend(to_addr=to_addr, username=username, card_url=card_url)

    raise RuntimeError(f"unsupported onboarding email provider: {provider!r}")
