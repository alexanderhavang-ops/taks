from __future__ import annotations

import html
import json
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse

from takctl.onboarding.http import external_base
from takctl.onboarding.onboarding_db import maybe_db
from takctl.onboarding.service_builder import build_service
from takctl.onboarding.emailer import send_onboarding_email
from takctl.onboarding.selection import load_selection, save_selection
from takctl.config import load_config
from takctl.onboarding.selection import load_selection
from takctl.onboarding.soldier_card.page import render_soldier_card_page, render_soldier_card_print_pack

router = APIRouter(tags=["onboarding"])


def _esc(v: Any) -> str:
    return html.escape("" if v is None else str(v), quote=True)


def _groups_from_card(card: dict) -> list[str]:
    m = (card or {}).get("marti") or {}
    gs = m.get("groups") or []
    return gs if isinstance(gs, list) else []


def _callsign_from_card(card: dict) -> str:
    h = (card or {}).get("header") or {}
    return str(h.get("callsign") or "—")


def _team_from_card(card: dict) -> str:
    h = (card or {}).get("header") or {}
    return str(h.get("team") or "—")


def _activity_age_from_card(card: dict) -> str:
    act = (card or {}).get("activity") or {}
    return str(act.get("age_human") or "—")


def _onboard_status_from_card(card: dict) -> str:
    return str((card or {}).get("onboarding_status") or "—")


def _unit_title_from_card(card: dict) -> str:
    gs = _groups_from_card(card)
    if gs:
        return str(gs[0])
    return "TAKS"


def _logo_html(base: str) -> str:
    png_url = f"{base}/assets/unit-current.png"
    svg_url = f"{base}/assets/unit-current.svg"
    return (
        f'<img class="unit-logo" src="{_esc(png_url)}" '
        f'onerror="this.onerror=null;this.src=\'{_esc(svg_url)}\';" '
        f'alt="Unit logo"/>'
    )


def _reveal_password_for_print_mode(print_mode: str) -> bool:
    return str(print_mode or "").strip() in ("passwords", "cards_inline_passwords", "cards_then_passwords")


def _email_from_identity(ident) -> str:
    try:
        ctx = getattr(ident, "ctx", {}) or {}
    except Exception:
        ctx = {}
    if not isinstance(ctx, dict):
        ctx = {}
    return str(ctx.get("email") or "").strip()


def _record_onboarding_email(username: str, *, email: str, card_url: str, print_mode: str, reveal_password: bool, delivery: str) -> None:
    try:
        sel = load_selection(username) or {}
        if not isinstance(sel, dict):
            sel = {}
        sel["last_onboarding_email"] = {
            "sent_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "email": str(email or "").strip(),
            "card_url": str(card_url or "").strip(),
            "print_mode": str(print_mode or "").strip(),
            "reveal_password": bool(reveal_password),
            "delivery": str(delivery or "").strip(),
        }
        save_selection(username, sel)
    except Exception:
        pass


def _issue_card_link_base(base: str, svc, *, username: str, ttl_sec: int, reveal_password: bool) -> dict[str, Any]:
    if hasattr(svc.store, "create_card_token"):
        ct = svc.store.create_card_token(
            username=username,
            ttl_sec=int(ttl_sec),
            reveal_password=bool(reveal_password),
        )
    else:
        ct = svc.store.upsert_card_token(
            username=username,
            ttl_sec=int(ttl_sec),
            reveal_password=bool(reveal_password),
        )

    card_url = f"{base}/api/onboarding/cards/{ct.token}"
    return {"card_token": {"token": ct.token}, "card_url": card_url}


def _render_card_page(*, base: str, username: str, card: dict, card_url: str, token: str, show_password: bool, password_value: str | None) -> str:
    bump = str(int(time.time()))

    callsign = _callsign_from_card(card)
    team = _team_from_card(card)
    age = _activity_age_from_card(card)
    onboard = _onboard_status_from_card(card)
    groups = ", ".join(_groups_from_card(card)) or "—"
    unit_title = _unit_title_from_card(card)

    qr_png = f"{base}/api/onboarding/cards/{token}/packages/atak/qr.png?b={_esc(bump)}"

    pw_html = ""
    if show_password:
        pw_html = f"""
        <div class="row">
          <div class="label">Password</div>
          <div class="value mono password">{_esc(password_value or "—")}</div>
        </div>
        """

    return f"""
<section class="page">
  <div class="sheet">

    <div class="credential-shell">

      <div class="credential-topbar">
        <div class="topbar-left">
          <div class="crest-wrap">
            {_logo_html(base)}
          </div>
          <div class="title-block">
            <div class="eyebrow">{_esc(unit_title)}</div>
            <div class="title">TAKS FIELD ACCESS CARD</div>
            <div class="subtitle">{_esc(username)}</div>
          </div>
        </div>
        <div class="topbar-right">
          <div class="status-tag">ACTIVE</div>
        </div>
      </div>

      <div class="grid">

        <div class="box data-box">
          <div class="section-title">Identity</div>

          <div class="row"><div class="label">Username</div><div class="value mono">{_esc(username)}</div></div>
          <div class="row"><div class="label">Callsign</div><div class="value mono strong">{_esc(callsign)}</div></div>
          <div class="row"><div class="label">Team</div><div class="value">{_esc(team)}</div></div>
          <div class="row"><div class="label">Groups</div><div class="value">{_esc(groups)}</div></div>
          <div class="row"><div class="label">Onboarding</div><div class="value">{_esc(onboard)}</div></div>
          <div class="row"><div class="label">Last seen</div><div class="value">{_esc(age)}</div></div>
          {pw_html}
        </div>

        <div class="box qr-box">
          <div class="section-title">ATAK Import</div>
          <div class="qrwrap">
            <img src="{_esc(qr_png)}" alt="ATAK QR"/>
          </div>
          <div class="qr-help">Scan QR to import server and identity defaults.</div>
        </div>

      </div>

      <div class="box link-box">
        <div class="section-title">Manual Fallback</div>
        <div class="row">
          <div class="label">Card link</div>
          <div class="value mono break">{_esc(card_url)}</div>
        </div>
        <div class="small">If QR is unavailable, open the card link manually.</div>
      </div>

    </div>

  </div>
</section>
"""


def _render_password_page(*, base: str, username: str, card: dict, password_value: str | None) -> str:
    callsign = _callsign_from_card(card)
    team = _team_from_card(card)
    groups = ", ".join(_groups_from_card(card)) or "—"
    unit_title = _unit_title_from_card(card)

    return f"""
<section class="page">
  <div class="sheet">

    <div class="credential-shell">

      <div class="credential-topbar">
        <div class="topbar-left">
          <div class="crest-wrap">
            {_logo_html(base)}
          </div>
          <div class="title-block">
            <div class="eyebrow">{_esc(unit_title)}</div>
            <div class="title">TAKS PASSWORD SLIP</div>
            <div class="subtitle">{_esc(username)}</div>
          </div>
        </div>
        <div class="topbar-right">
          <div class="status-tag warn">SENSITIVE</div>
        </div>
      </div>

      <div class="box password-box">
        <div class="section-title">Credentials</div>
        <div class="row"><div class="label">Username</div><div class="value mono">{_esc(username)}</div></div>
        <div class="row"><div class="label">Callsign</div><div class="value mono strong">{_esc(callsign)}</div></div>
        <div class="row"><div class="label">Team</div><div class="value">{_esc(team)}</div></div>
        <div class="row"><div class="label">Groups</div><div class="value">{_esc(groups)}</div></div>
        <div class="row password-row"><div class="label">Password</div><div class="value mono password big break">{_esc(password_value or "—")}</div></div>
      </div>

    </div>

  </div>
</section>
"""


def _render_print_pack(*, title: str, sections: list[str]) -> str:
    body = "\n".join(sections) if sections else """
<section class="page">
  <div class="sheet">
    <div class="credential-shell">
      <div class="credential-topbar">
        <div class="title-block">
          <div class="eyebrow">TAKS</div>
          <div class="title">NO USERS SELECTED</div>
        </div>
      </div>
    </div>
  </div>
</section>
"""

    return f"""
<!doctype html>
<html>
<head>
<meta charset="utf-8"/>
<title>{_esc(title)}</title>

<style>
body {{
  margin: 0;
  background: #e9e9e9;
  font-family: Arial, Helvetica, sans-serif;
  color: #111;
}}

.page {{
  width: 210mm;
  min-height: 297mm;
  margin: 0 auto;
  background: #fff;
  page-break-after: always;
  break-after: page;
}}

.sheet {{
  padding: 12mm;
}}

.credential-shell {{
  border: 1px solid #cfcfcf;
  border-radius: 10px;
  overflow: hidden;
  background: #fff;
}}

.credential-topbar {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  background: linear-gradient(180deg, #1f2328 0%, #111418 100%);
  color: #fff;
  border-bottom: 3px solid #b08d2f;
}}

.topbar-left {{
  display: flex;
  align-items: center;
  gap: 14px;
  min-width: 0;
}}

.crest-wrap {{
  flex: 0 0 auto;
  width: 54px;
  height: 54px;
  display: flex;
  align-items: center;
  justify-content: center;
}}

.unit-logo {{
  max-width: 54px;
  max-height: 54px;
  width: auto;
  height: auto;
  display: block;
}}

.title-block {{
  min-width: 0;
}}

.eyebrow {{
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: rgba(255,255,255,0.72);
  font-weight: 700;
}}

.title {{
  font-size: 28px;
  font-weight: 900;
  line-height: 1.05;
  margin-top: 2px;
}}

.subtitle {{
  font-size: 16px;
  color: rgba(255,255,255,0.82);
  margin-top: 3px;
}}

.status-tag {{
  border: 1px solid rgba(255,255,255,0.30);
  padding: 6px 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.08em;
}}

.status-tag.warn {{
  color: #fff3cd;
  border-color: rgba(255,243,205,0.45);
}}

.grid {{
  display: grid;
  grid-template-columns: minmax(0, 1.05fr) minmax(0, 0.95fr);
  gap: 14px;
  padding: 14px;
}}

.box {{
  border: 1px solid #d8d8d8;
  border-radius: 10px;
  padding: 14px;
  overflow: hidden;
  background: #fff;
}}

.section-title {{
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.09em;
  color: #6d7278;
  font-weight: 800;
  margin-bottom: 12px;
}}

.row {{
  display: grid;
  grid-template-columns: 140px minmax(0,1fr);
  align-items: center;
  gap: 10px;
  margin-bottom: 9px;
}}

.label {{
  font-size: 11px;
  color: #6d7278;
  font-weight: 800;
  text-transform: uppercase;
  white-space: nowrap;
  letter-spacing: 0.04em;
}}

.value {{
  font-size: 15px;
  line-height: 1.25;
}}

.strong {{
  font-weight: 800;
}}

.password {{
  font-weight: 800;
}}

.big {{
  font-size: 24px;
  line-height: 1.15;
}}

.mono {{
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}}

.break {{
  word-break: break-all;
}}

.qr-box {{
  display: flex;
  flex-direction: column;
  align-items: center;
}}

.qrwrap {{
  width: 100%;
  display: flex;
  justify-content: center;
  padding: 4px 0 8px 0;
}}

.qrwrap img {{
  max-width: 88mm;
  width: 100%;
  height: auto;
  display: block;
}}

.qr-help {{
  font-size: 12px;
  color: #555;
  text-align: center;
}}

.link-box {{
  margin: 0 14px 14px 14px;
}}

.small {{
  font-size: 12px;
  color: #555;
  margin-top: 6px;
}}

.password-box {{
  margin: 14px;
}}

.password-row {{
  margin-top: 14px;
  padding-top: 10px;
  border-top: 1px dashed #cfcfcf;
}}

@media print {{
  body {{
    background: #fff;
  }}
  .page {{
    margin: 0;
  }}
}}
</style>

</head>
<body>
{body}
</body>
</html>
"""


@router.get("/onboarding/users/{username}/card")
def onboarding_user_card(username: str, recent_minutes: int = Query(120, ge=1, le=24 * 60)):
    svc = build_service()
    db, _, _, _ = maybe_db()

    try:
        card = svc.user_card(username=username, db=db, recent_minutes=int(recent_minutes))
    except KeyError:
        raise HTTPException(status_code=404, detail="Unknown user")

    return JSONResponse({"card": card})



@router.post("/onboarding/email-pack")
async def onboarding_email_pack(req: Request):
    body = await req.json()
    usernames = body.get("usernames") or []
    print_mode = str(body.get("print_mode") or "cards")
    reveal_password = _reveal_password_for_print_mode(print_mode)

    svc = build_service()
    base = external_base(req).rstrip("/")
    cfg = load_config()
    lang = str(cfg.get("language", "sv") or "sv").strip().lower()
    ttl_sec = int(cfg.get("onboarding_print_card_ttl_sec", 600) or 600)

    sent = 0
    failed = 0
    missing_email = 0
    results = []

    for username in usernames:
        username = str(username or "").strip()
        if not username:
            continue

        ident = svc.store.get_identity(username)
        email = _email_from_identity(ident)
        if not email:
            missing_email += 1
            results.append({
                "username": username,
                "status": "missing_email",
            })
            continue

        try:
            card_info = _issue_card_link_base(
                base,
                svc,
                username=username,
                ttl_sec=ttl_sec,
                reveal_password=reveal_password,
            )
            email_status = send_onboarding_email(
                to_addr=email,
                username=username,
                card_url=str(card_info.get("card_url") or ""),
                lang=lang,
            )
            _record_onboarding_email(
                username,
                email=email,
                card_url=str(card_info.get("card_url") or ""),
                print_mode=print_mode,
                reveal_password=reveal_password,
                delivery=str((email_status or {}).get("delivery") or ""),
            )
            sent += 1
            results.append({
                "username": username,
                "email": email,
                "status": "sent",
                "email_status": email_status,
                **card_info,
            })
        except Exception as e:
            failed += 1
            results.append({
                "username": username,
                "email": email,
                "status": "failed",
                "error": str(e),
            })

    return JSONResponse({
        "ok": True,
        "print_mode": print_mode,
        "reveal_password": reveal_password,
        "sent": sent,
        "failed": failed,
        "missing_email": missing_email,
        "results": results,
    })


@router.post("/onboarding/print-pack")
async def onboarding_print_pack(req: Request, payload: str = Form(...)):
    body = json.loads(payload or "{}")

    usernames = body.get("usernames") or []
    print_mode = str(body.get("print_mode") or "cards").strip()

    svc = build_service()
    db, _, _, _ = maybe_db()
    base = external_base(req).rstrip("/")

    cfg = load_config()
    lang = str(cfg.get("language", "sv") or "sv").strip().lower()
    ttl_sec = int(getattr(cfg, "onboarding_print_card_ttl_sec", 600) or 600)

    sections_cards: list[str] = []
    sections_passwords: list[str] = []

    for username in usernames:
        username = str(username or "").strip()
        if not username:
            continue

        try:
            card = svc.user_card(username=username, db=db, recent_minutes=120)
        except KeyError:
            continue

        lifecycle = card.get("lifecycle") if isinstance(card, dict) else None

        groups = []
        if isinstance(card, dict):
            m = card.get("marti") or {}
            if isinstance(m, dict) and isinstance(m.get("groups"), list):
                groups = m.get("groups") or []
        if not isinstance(groups, list):
            groups = []

        ident = svc.store.get_identity(username)
        sel = load_selection(username) or {}

        reveal_password = print_mode in ("cards_inline_passwords", "passwords", "cards_then_passwords")

        card_info = _issue_card_link_base(
            base,
            svc,
            username=username,
            ttl_sec=ttl_sec,
            reveal_password=reveal_password,
        )

        token = str(((card_info.get("card_token") or {}).get("token") or "")).strip()
        if not token:
            continue

        ct = svc.store.get_card_token(token)
        if ct is None:
            continue

        exp = getattr(ct, "expires_at_utc", None) or getattr(ct, "expires_at", None)
        if exp is None:
            continue

        if print_mode in ("cards", "cards_inline_passwords", "cards_then_passwords"):
            sections_cards.append(
                render_soldier_card_page(
                    lang=lang,
                    username=username,
                    groups=groups,
                    base=base,
                    sel=sel,
                    ident=ident,
                    token=token,
                    expires_at_utc=exp,
                    reveal_password=reveal_password,
                    lifecycle=lifecycle,
                    render_mode="print_full",
                )
            )

        if print_mode in ("passwords", "cards_then_passwords"):
            sections_passwords.append(
                render_soldier_card_page(
                    lang=lang,
                    username=username,
                    groups=groups,
                    base=base,
                    sel=sel,
                    ident=ident,
                    token=token,
                    expires_at_utc=exp,
                    reveal_password=True,
                    lifecycle=lifecycle,
                    render_mode="print_password",
                )
            )

    if print_mode == "passwords":
        sections = sections_passwords
    elif print_mode == "cards_then_passwords":
        sections = sections_cards + sections_passwords
    else:
        sections = sections_cards

    html_doc = render_soldier_card_print_pack(title="TAKS print pack", sections=sections)

    return HTMLResponse(html_doc)


