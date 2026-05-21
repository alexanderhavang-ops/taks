from __future__ import annotations

from html import escape as h

from takctl.onboarding.soldier_card.common import boolpill, code, ctx_from, fmt_dt, getv, norm, pill, row, safe
from takctl.onboarding.soldier_card.i18n import t


def profile_block(*, lang: str | None, username: str, groups: list[str], sel: dict, ident) -> str:
    ctx = ctx_from(ident, sel)

    callsign = norm(getv(ident, "callsign")) or safe(username)
    team = norm(ctx.get("team"))
    atak_role = norm(ctx.get("atak_role_type")) or norm(ctx.get("role"))
    remarks = norm(ctx.get("remarks"))

    battalion = norm(ctx.get("battalion"))
    battalion_fal = norm(ctx.get("battalion_fal"))
    company = norm(ctx.get("company"))
    platoon = norm(ctx.get("platoon"))
    group = norm(ctx.get("group"))
    n = norm(ctx.get("n"))

    groups_txt = ", ".join(groups or [])

    unit_bits = []
    if battalion_fal:
        unit_bits.append(battalion_fal)
    if battalion:
        unit_bits.append(f"{battalion} HVBAT")
    if company:
        unit_bits.append(t(lang, "unit.company", n=company))
    if platoon:
        unit_bits.append(t(lang, "unit.platoon", n=platoon))
    if group:
        unit_bits.append(t(lang, "unit.group", n=group))
    if n:
        unit_bits.append(f"EN {n}")

    header_right = []
    if team:
        header_right.append(pill(team, "team"))
    if atak_role:
        header_right.append(pill(atak_role, "meta"))

    rows = []
    rows.append(
        f'<div class="kvrow"><div class="kvlabel">{h(t(lang, "field.username"))}</div>'
        f'<div class="kvvalue"><code id="taks_username">{h(safe(username))}</code> '
        f'<button class="btn interactive-only" onclick="copyId(\'taks_username\')">{h(t(lang, "soldier.copy"))}</button></div></div>'
    )

    if remarks:
        rows.append(
            f'<div class="kvrow"><div class="kvlabel">{h(t(lang, "field.remarks"))}</div>'
            f'<div class="kvvalue"><code>{h(remarks)}</code></div></div>'
        )

    if groups_txt:
        rows.append(
            f'<div class="kvrow"><div class="kvlabel">{h(t(lang, "field.groups"))}</div>'
            f'<div class="kvvalue"><code>{h(groups_txt)}</code></div></div>'
        )

    return (
        '<div class="profile-card">'
        '<style>'
        '.profile-card{display:flex;flex-direction:column;gap:14px;}'
        '.profile-hero{background:linear-gradient(135deg, rgba(42,84,144,0.88), rgba(20,55,104,0.88));'
        'border:1px solid rgba(139,184,255,0.18);border-radius:14px;padding:14px 16px;box-shadow:0 10px 24px rgba(0,0,0,0.20);}'
        '.profile-hero-top{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;flex-wrap:wrap;}'
        '.profile-callsign{font-size:28px;font-weight:850;line-height:1.0;letter-spacing:0.5px;}'
        '.profile-unitline{margin-top:6px;font-size:13px;color:rgba(255,255,255,0.92);font-weight:600;}'
        '.profile-pills{display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end;}'
        '.profile-body{display:flex;flex-direction:column;gap:10px;}'
        '.kvrow{display:grid;grid-template-columns:140px 1fr;gap:12px;align-items:start;}'
        '.kvlabel{font-size:12px;color:rgba(255,255,255,0.68);font-weight:700;text-transform:uppercase;letter-spacing:0.04em;}'
        '.kvvalue{font-size:14px;color:rgba(255,255,255,0.94);line-height:1.45;word-break:break-word;}'
        '@media (max-width: 640px){.kvrow{grid-template-columns:1fr;gap:4px;}}'
        '</style>'
        f'<div class="profile-hero">'
        f'  <div class="profile-hero-top">'
        f'    <div>'
        f'      <div class="profile-callsign">{h(callsign)}</div>'
        f'      <div class="profile-unitline">{h(" · ".join(unit_bits) if unit_bits else safe(username))}</div>'
        f'    </div>'
        f'    <div class="profile-pills">{"".join(header_right)}</div>'
        f'  </div>'
        f'</div>'
        f'<div class="profile-body">{"".join(rows)}</div>'
        '</div>'
    )


def password_block(
    *,
    lang: str | None,
    username: str,
    ident,
    reveal_password: bool,
    truststore_password: str | None = None,
    client_password: str | None = None,
) -> str:
    if ident is None:
        return f"""
<div class="note">
  {h(t(lang, "pw.unknown_no_record"))}<br/>
  {h(t(lang, "pw.marti_note"))}
</div>
"""

    origin = getv(ident, "origin", "marti")
    pw_known = bool(getv(ident, "password_known", False))
    pw_val = getv(ident, "password", None) if pw_known else None

    if (not pw_known) or (origin != "taks"):
        return f"""
<div class="note">
  {h(t(lang, "pw.unknown_origin", origin=safe(origin)))}<br/>
  {h(t(lang, "pw.external_note"))}
</div>
"""

    if not reveal_password:
        return f"""
<div class="note">
  {h(t(lang, "field.username"))}: <code id="taks_username2">{h(safe(username))}</code>
  <button class="btn interactive-only" onclick="copyId('taks_username2')">{h(t(lang, "soldier.copy"))}</button><br/>
  {h(t(lang, "pw.hidden"))}
</div>
"""

    extra = ""
    if truststore_password:
        extra += (
            f'<br/>{h(t(lang, "pw.truststore_password"))}: '
            f'<code id="taks_truststore_password">{h(safe(truststore_password))}</code> '
            f'<button class="btn interactive-only" onclick="copyId(\'taks_truststore_password\')">{h(t(lang, "soldier.copy"))}</button>'
        )
    if client_password:
        extra += (
            f'<br/>{h(t(lang, "pw.client_password"))}: '
            f'<code id="taks_client_password">{h(safe(client_password))}</code> '
            f'<button class="btn interactive-only" onclick="copyId(\'taks_client_password\')">{h(t(lang, "soldier.copy"))}</button>'
        )

    return f"""
<div class="note">
  {h(t(lang, "field.username"))}: <code id="taks_username2">{h(safe(username))}</code>
  <button class="btn interactive-only" onclick="copyId('taks_username2')">{h(t(lang, "soldier.copy"))}</button><br/>
  {h(t(lang, "pw.password"))}: <code id="taks_password">{h(safe(pw_val))}</code>
  <button class="btn interactive-only" onclick="copyId('taks_password')">{h(t(lang, "soldier.copy"))}</button>{extra}
</div>
"""


def lifecycle_block(lang: str | None, lifecycle: dict | None) -> str:
    if not isinstance(lifecycle, dict) or not lifecycle:
        return f'<div class="note">{h(t(lang, "lc.none"))}</div>'

    stage = norm(lifecycle.get("stage"))
    label = norm(lifecycle.get("label"))
    ev = lifecycle.get("evidence") or {}
    if not isinstance(ev, dict):
        ev = {}

    headline = stage or ""
    if label:
        headline = f"{headline} — {label}" if headline else label
    if not headline:
        headline = t(lang, "soldier.lifecycle")

    parts: list[str] = []
    parts.append(f'<div class="note"><div class="row"><b>{h(t(lang, "lc.head"))}</b>: <code>{h(headline)}</code></div>')

    taks_origin = norm(ev.get("taks_origin"))
    taks_pw_known = bool(ev.get("taks_password_known"))
    onboarding_status = norm((ev.get("onboarding") or {}).get("status"))
    offboarded = bool(ev.get("offboarded"))

    small = []
    if taks_origin:
        small.append(row(t(lang, "lc.taks_origin"), code(taks_origin)))
    if onboarding_status:
        small.append(row(t(lang, "lc.onboarding_status"), code(onboarding_status)))
    small.append(row(t(lang, "lc.password_known"), boolpill(taks_pw_known)))
    small.append(row(t(lang, "lc.offboarded"), boolpill(offboarded)))

    small = [s for s in small if s]
    if small:
        parts.append('<hr/>')
        parts.extend(small)

    cot_seen = bool(ev.get("cot_seen"))
    seen_recently = bool(ev.get("seen_recently"))
    act = ev.get("activity")
    if not isinstance(act, dict):
        act = {}

    cot_last = act.get("last_cot_time") or ev.get("last_cot_time")
    cot_stale = act.get("stale") or ev.get("stale")
    cot_uid = act.get("uid") or ev.get("cot_uid")
    cot_callsign = act.get("callsign") or ev.get("cot_callsign")
    cot_age = act.get("age_human") or ev.get("age_human")
    cot_is_current = act.get("is_current") if "is_current" in act else ev.get("is_current")

    cot_rows = []
    cot_rows.append(row(t(lang, "lc.cot_seen"), boolpill(cot_seen)))
    cot_rows.append(row(t(lang, "lc.seen_recently"), boolpill(seen_recently)))
    if cot_callsign:
        cot_rows.append(row(t(lang, "lc.cot_callsign"), code(cot_callsign)))
    if cot_uid:
        cot_rows.append(row(t(lang, "lc.cot_uid"), code(cot_uid)))
    if cot_last:
        cot_rows.append(row(t(lang, "lc.last_cot"), fmt_dt(cot_last)))
    if cot_stale:
        cot_rows.append(row(t(lang, "lc.stale"), fmt_dt(cot_stale)))
    if cot_age:
        cot_rows.append(row(t(lang, "lc.age"), code(cot_age)))
    if cot_is_current is not None:
        cot_rows.append(row(t(lang, "lc.is_current"), boolpill(bool(cot_is_current))))

    cot_rows = [r for r in cot_rows if r]
    if cot_rows:
        parts.append('<hr/>')
        parts.append(f'<div class="row"><b>{h(t(lang, "lc.cot_block"))}</b>: <span class="muted">{h(t(lang, "lc.cot_sub"))}</span></div>')
        parts.extend(cot_rows)

    marti = ev.get("marti_client") or {}
    if not isinstance(marti, dict):
        marti = {}

    latest_ep = marti.get("latest_endpoint") or {}
    if not isinstance(latest_ep, dict):
        latest_ep = {}

    latest_evt = marti.get("latest_endpoint_event") or {}
    if not isinstance(latest_evt, dict):
        latest_evt = {}

    latest_cert = marti.get("latest_cert") or {}
    if not isinstance(latest_cert, dict):
        latest_cert = {}

    m_rows = []
    m_rows.append(row(t(lang, "lc.has_endpoint"), boolpill(bool(marti.get("has_endpoint")))))
    m_rows.append(row(t(lang, "lc.has_endpoint_event"), boolpill(bool(marti.get("has_endpoint_event")))))
    m_rows.append(row(t(lang, "lc.has_certificate"), boolpill(bool(marti.get("has_certificate")))))
    if marti.get("endpoints_n") is not None:
        m_rows.append(row(t(lang, "lc.endpoints"), code(marti.get("endpoints_n"))))
    if marti.get("certs_by_user_dn_n") is not None:
        m_rows.append(row(t(lang, "lc.certs_by_user_dn"), code(marti.get("certs_by_user_dn_n"))))
    if marti.get("certs_by_client_uid_n") is not None:
        m_rows.append(row(t(lang, "lc.certs_by_client_uid"), code(marti.get("certs_by_client_uid_n"))))
    if marti.get("certs_revoked_n") is not None:
        m_rows.append(row(t(lang, "lc.certs_revoked"), code(marti.get("certs_revoked_n"))))

    if latest_ep:
        ep_bits = []
        if latest_ep.get("callsign"):
            ep_bits.append(f"callsign={norm(latest_ep.get('callsign'))}")
        if latest_ep.get("uid"):
            ep_bits.append(f"uid={norm(latest_ep.get('uid'))}")
        if latest_ep.get("id") is not None:
            ep_bits.append(f"id={norm(latest_ep.get('id'))}")
        if ep_bits:
            m_rows.append(row(t(lang, "lc.latest_endpoint"), code(", ".join(ep_bits))))

    if latest_evt:
        evt_bits = []
        if latest_evt.get("created_ts"):
            evt_bits.append(f"ts={norm(latest_evt.get('created_ts'))}")
        if latest_evt.get("client_version"):
            evt_bits.append(f"ver={norm(latest_evt.get('client_version'))}")
        if latest_evt.get("connection_event_type_id") is not None:
            evt_bits.append(f"type={norm(latest_evt.get('connection_event_type_id'))}")
        if latest_evt.get("client_endpoint_id") is not None:
            evt_bits.append(f"ep_id={norm(latest_evt.get('client_endpoint_id'))}")
        if latest_evt.get("id") is not None:
            evt_bits.append(f"id={norm(latest_evt.get('id'))}")
        if evt_bits:
            m_rows.append(row(t(lang, "lc.latest_endpoint_event"), code(", ".join(evt_bits))))

    if latest_cert:
        cert_bits = []
        if latest_cert.get("client_uid"):
            cert_bits.append(f"uid={norm(latest_cert.get('client_uid'))}")
        if latest_cert.get("issuance_date"):
            cert_bits.append(f"issued={norm(latest_cert.get('issuance_date'))}")
        if latest_cert.get("effective_date"):
            cert_bits.append(f"eff={norm(latest_cert.get('effective_date'))}")
        if latest_cert.get("expiration_date"):
            cert_bits.append(f"exp={norm(latest_cert.get('expiration_date'))}")
        if latest_cert.get("revocation_date"):
            cert_bits.append(f"revoked={norm(latest_cert.get('revocation_date'))}")
        if cert_bits:
            m_rows.append(row(t(lang, "lc.latest_certificate"), code(", ".join(cert_bits))))

    m_rows = [r for r in m_rows if r]
    if m_rows:
        parts.append('<hr/>')
        parts.append(f'<div class="row"><b>{h(t(lang, "lc.marti_block"))}</b>: <span class="muted">{h(t(lang, "lc.marti_sub"))}</span></div>')
        parts.extend(m_rows)

    art = ev.get("artifacts") or {}
    if not isinstance(art, dict):
        art = {}

    a_rows = []
    if "present" in art:
        a_rows.append(row(t(lang, "lc.artifacts_present"), boolpill(bool(art.get("present")))))
    if art.get("artifacts_root"):
        a_rows.append(row(t(lang, "lc.artifacts_path"), code(art.get("artifacts_root"))))
    if "atak_package_zip" in art:
        a_rows.append(row(t(lang, "lc.atak_package_zip"), boolpill(bool(art.get("atak_package_zip")))))
    if "atak_package_creds_zip" in art:
        a_rows.append(row(t(lang, "lc.atak_package_creds_zip"), boolpill(bool(art.get("atak_package_creds_zip")))))
    if "any_qr_png" in art:
        a_rows.append(row(t(lang, "lc.any_qr_png"), boolpill(bool(art.get("any_qr_png")))))

    a_rows = [r for r in a_rows if r]
    if a_rows:
        parts.append('<hr/>')
        parts.append(f'<div class="row"><b>{h(t(lang, "lc.artifacts_block"))}</b>: <span class="muted">{h(t(lang, "lc.artifacts_sub"))}</span></div>')
        parts.extend(a_rows)

    parts.append("</div>")
    return "".join(parts)
