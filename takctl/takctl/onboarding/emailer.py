from __future__ import annotations

import json
import re
import subprocess
from email.message import EmailMessage
from html import escape as h
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
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


def _default_lang() -> str:
    raw = _cfg_get("language", "sv").strip().lower()
    if raw.startswith("en"):
        return "en"
    return "sv"


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


def _base_from_card_url(card_url: str) -> str:
    u = urlsplit(card_url or "")
    if not u.scheme or not u.netloc:
        raise RuntimeError(f"invalid card_url for email template: {card_url!r}")
    return f"{u.scheme}://{u.netloc}"


def _read_brand() -> dict:
    candidates = [
        Path("/opt/tak/tools/takctl/web/assets/brand.json"),
        Path("/opt/taks/takctl/web/assets/brand.json"),
        Path("/opt/taks/web/assets/brand.json"),
    ]
    for p in candidates:
        try:
            if p.exists():
                return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _branding(card_url: str) -> dict[str, str]:
    base = _base_from_card_url(card_url)
    brand = _read_brand() or {}
    slogan = str(brand.get("slogan") or "").strip()

    return {
        "base": base,
        "taks_logo_url": f"{base}/assets/taks-logo.png",
        "unit_logo_url": f"{base}/assets/unit-current.png",
        "slogan": slogan,
    }


def _card_qr_url(card_url: str) -> str:
    base = _base_from_card_url(card_url)
    token = str(card_url.rstrip("/").rsplit("/", 1)[-1] or "").strip()
    if not token:
        raise RuntimeError(f"invalid card_url token: {card_url!r}")
    return f"{base}/api/onboarding/cards/{token}/card-url/qr.png"


def _lang_copy(lang: str) -> dict[str, str]:
    if (lang or "").lower().startswith("en"):
        return {
            "subject": "Welcome to TAKS",
            "eyebrow": "TAKS ONBOARDING",
            "headline": "Welcome to your unit",
            "lead": "Your onboarding card is ready. Open the link below to start your setup in ATAK, iTAK, or in a browser.",
            "cta": "Open soldier card",
            "expires": "This link may expire, so use it soon.",
            "username": "User",
            "qr_title": "Scan QR",
            "qr_help": "Open the same soldier card on another device.",
            "manual_link": "Direct link",
            "closing": "Stay ready.",
            "footer": "This message was sent by TAKS onboarding.",
        }
    return {
        "subject": "Välkommen till TAKS",
        "eyebrow": "TAKS ONBOARDING",
        "headline": "Välkommen till ditt förband",
        "lead": "Ditt soldatkort är klart. Öppna länken nedan för att starta onboarding i ATAK, iTAK eller i webbläsare.",
        "cta": "Öppna soldatkort",
        "expires": "Länken kan gå ut, så använd den så snart som möjligt.",
        "username": "Användare",
        "qr_title": "Skanna QR",
        "qr_help": "Öppna samma soldatkort på en annan enhet.",
        "manual_link": "Direktlänk",
        "closing": "Var redo.",
        "footer": "Detta meddelande skickades av TAKS onboarding.",
    }


def _subject(username: str, lang: str) -> str:
    c = _lang_copy(lang)
    return f"{c['subject']} — {username}"


def _text_body(*, username: str, card_url: str, lang: str) -> str:
    c = _lang_copy(lang)
    b = _branding(card_url)
    slogan = f"{b['slogan']}\n\n" if b["slogan"] else ""
    return (
        f"{c['subject']}\n"
        f"{slogan}"
        f"{c['headline']}\n\n"
        f"{c['username']}: {username}\n\n"
        f"{c['lead']}\n\n"
        f"{card_url}\n\n"
        f"{c['expires']}\n\n"
        f"{c['closing']}\n"
        f"/TAKS\n"
    )


def _html_body(*, username: str, card_url: str, lang: str) -> str:
    c = _lang_copy(lang)
    b = _branding(card_url)
    qr_url = _card_qr_url(card_url)

    slogan_html = (
        f'<div style="margin-top:8px;font-size:12px;letter-spacing:0.12em;'
        f'text-transform:uppercase;color:#b7c0ce;">{h(b["slogan"])}</div>'
        if b["slogan"] else ""
    )

    return f"""<!doctype html>
<html lang="{h(lang)}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{h(c["subject"])}</title>
</head>
<body style="margin:0;padding:0;background:#0b0f14;color:#e8edf5;font-family:Arial,Helvetica,sans-serif;">
  <div style="display:none;max-height:0;overflow:hidden;opacity:0;">
    {h(c["headline"])} — {h(username)}
  </div>

  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:#0b0f14;">
    <tr>
      <td align="center" style="padding:32px 16px;">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="max-width:760px;">
          <tr>
            <td style="padding:0 0 18px 0;">
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                <tr>
                  <td valign="middle" style="padding-right:16px;">
                    <img src="{h(b['taks_logo_url'])}" alt="TAKS" style="height:42px;width:auto;display:block;border:0;">
                  </td>
                  <td valign="middle" align="right">
                    <img src="{h(b['unit_logo_url'])}" alt="Unit" style="max-height:54px;max-width:220px;width:auto;display:block;border:0;">
                  </td>
                </tr>
              </table>
              {slogan_html}
            </td>
          </tr>

          <tr>
            <td style="background:linear-gradient(180deg,#131922,#0f141b);border:1px solid #263140;border-radius:20px;padding:28px;box-shadow:0 18px 48px rgba(0,0,0,0.35);">
              <div style="font-size:12px;letter-spacing:0.14em;text-transform:uppercase;color:#8fb3ff;font-weight:bold;">
                {h(c["eyebrow"])}
              </div>

              <div style="margin-top:10px;font-size:32px;line-height:1.15;font-weight:800;color:#f5f7fb;">
                {h(c["headline"])}
              </div>

              <div style="margin-top:14px;font-size:16px;line-height:1.6;color:#d4dbea;">
                {h(c["lead"])}
              </div>

              <table role="presentation" cellspacing="0" cellpadding="0" border="0" style="margin-top:22px;">
                <tr>
                  <td style="font-size:13px;color:#9aa8bd;padding:0 0 6px 0;">
                    {h(c["username"])}
                  </td>
                </tr>
                <tr>
                  <td style="font-size:20px;font-weight:700;color:#ffffff;">
                    {h(username)}
                  </td>
                </tr>
              </table>

              <table role="presentation" cellspacing="0" cellpadding="0" border="0" style="margin-top:24px;">
                <tr>
                  <td style="border-radius:14px;background:#7fa8ff;">
                    <a href="{h(card_url)}"
                       style="display:inline-block;padding:14px 20px;font-size:15px;font-weight:700;color:#08111d;text-decoration:none;border-radius:14px;">
                      {h(c["cta"])}
                    </a>
                  </td>
                </tr>
              </table>

              <div style="margin-top:22px;padding:18px;background:#0c1117;border:1px solid #202835;border-radius:16px;">
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                  <tr>
                    <td valign="top" style="width:220px;padding-right:18px;">
                      <div style="font-size:13px;font-weight:700;color:#f5f7fb;padding-bottom:10px;">
                        {h(c["qr_title"])}
                      </div>
                      <img src="{h(qr_url)}" alt="{h(c["qr_title"])}" style="display:block;width:180px;max-width:100%;height:auto;background:#ffffff;padding:8px;border-radius:12px;border:0;">
                      <div style="margin-top:10px;font-size:12px;line-height:1.6;color:#aeb8c8;">
                        {h(c["qr_help"])}
                      </div>
                    </td>
                    <td valign="top" style="padding-left:6px;">
                      <div style="font-size:13px;font-weight:700;color:#f5f7fb;padding-bottom:10px;">
                        {h(c["manual_link"])}
                      </div>
                      <div style="font-size:13px;line-height:1.7;color:#aeb8c8;word-break:break-all;">
                        {h(card_url)}
                      </div>
                    </td>
                  </tr>
                </table>
              </div>

              <div style="margin-top:18px;padding:14px 16px;background:#0c1117;border:1px solid #202835;border-radius:14px;font-size:13px;line-height:1.6;color:#c7d0de;">
                {h(c["expires"])}
              </div>
            </td>
          </tr>

          <tr>
            <td style="padding:16px 6px 0 6px;font-size:12px;line-height:1.6;color:#95a2b7;">
              {h(c["closing"])}<br>
              {h(c["footer"])}
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""


def _send_via_sendmail(*, to_addr: str, username: str, card_url: str, lang: str) -> dict:
    msg = EmailMessage()
    msg["From"] = _from_addr()
    msg["To"] = to_addr
    msg["Subject"] = _subject(username, lang)

    reply_to = _reply_to()
    if reply_to:
        msg["Reply-To"] = reply_to

    msg.set_content(_text_body(username=username, card_url=card_url, lang=lang))
    msg.add_alternative(_html_body(username=username, card_url=card_url, lang=lang), subtype="html")

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
        "lang": lang,
    }


def _send_via_resend(*, to_addr: str, username: str, card_url: str, lang: str) -> dict:
    payload = {
        "from": _from_addr(),
        "to": [to_addr],
        "subject": _subject(username, lang),
        "text": _text_body(username=username, card_url=card_url, lang=lang),
        "html": _html_body(username=username, card_url=card_url, lang=lang),
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
        "subject": _subject(username, lang),
        "delivery": "resend",
        "lang": lang,
        "provider_response": out,
    }


def send_onboarding_email(*, to_addr: str, username: str, card_url: str, lang: str | None = None) -> dict:
    to_addr = (to_addr or "").strip()
    username = (username or "").strip()
    card_url = (card_url or "").strip()
    lang = (lang or _default_lang()).strip().lower()
    if not lang.startswith("en"):
        lang = "sv"
    else:
        lang = "en"

    if not is_valid_email(to_addr):
        raise RuntimeError(f"invalid email address: {to_addr!r}")
    if not username:
        raise RuntimeError("username required for onboarding email")
    if not card_url:
        raise RuntimeError("card_url required for onboarding email")

    provider = _provider()
    if provider == "sendmail":
        return _send_via_sendmail(to_addr=to_addr, username=username, card_url=card_url, lang=lang)
    if provider == "resend":
        return _send_via_resend(to_addr=to_addr, username=username, card_url=card_url, lang=lang)

    raise RuntimeError(f"unsupported onboarding_email_provider: {provider!r}")
