from __future__ import annotations

from datetime import datetime, timezone
from html import escape as _h

from takctl.onboarding.atak import atak_package_url


def _safe(v: object) -> str:
    return "" if v is None else str(v)


def _get(thing, key: str, default=None):
    """Safe getter for either objects (attrs) or dicts."""
    if thing is None:
        return default
    if isinstance(thing, dict):
        return thing.get(key, default)
    return getattr(thing, key, default)


def _ctx_from(ident, sel: dict) -> dict:
    """
    Prefer taks_identity.ctx (authoritative) then taks_identity.identity, then sel.ctx (fallback).
    """
    out: dict = {}

    ident_ctx = _get(ident, "ctx", None) or {}
    ident_identity = _get(ident, "identity", None) or {}

    if isinstance(ident_ctx, dict):
        out.update(ident_ctx)
    if isinstance(ident_identity, dict):
        for k, v in ident_identity.items():
            if k not in out and v is not None:
                out[k] = v

    sel_ctx = (sel or {}).get("ctx") or {}
    if isinstance(sel_ctx, dict):
        for k, v in sel_ctx.items():
            if k not in out and v is not None:
                out[k] = v

    return out


def _norm(s: object) -> str:
    return str(s).strip() if s is not None else ""


def _pill(text: str, cls: str = "") -> str:
    c = ("pill " + cls).strip()
    return f'<span class="{c}">{_h(text)}</span>'


def _row(label: str, html_value: str) -> str:
    if not html_value:
        return ""
    return f'<div class="row"><b>{_h(label)}</b>: {html_value}</div>'


def _code(v: object) -> str:
    if v is None:
        return ""
    s = _norm(v)
    if not s:
        return ""
    return f"<code>{_h(s)}</code>"


def _boolpill(v: bool, *, yes: str = "yes", no: str = "no") -> str:
    return _pill(yes if v else no, "meta")


def _fmt_dt(v: object) -> str:
    s = _norm(v)
    if not s:
        return ""
    # We keep it as-is (service already formats Z timestamps where possible)
    return _code(s)


def _profile_block(*, username: str, groups: list[str], sel: dict, ident) -> str:
    ctx = _ctx_from(ident, sel)

    callsign = _norm(ctx.get("callsign")) or _safe(username)
    team = _norm(ctx.get("team"))
    atak_role = _norm(ctx.get("atak_role_type")) or _norm(ctx.get("role"))
    remarks = _norm(ctx.get("remarks"))

    battalion = _norm(ctx.get("battalion"))
    battalion_fal = _norm(ctx.get("battalion_fal"))
    company = _norm(ctx.get("company"))
    platoon = _norm(ctx.get("platoon"))
    group = _norm(ctx.get("group"))
    n = _norm(ctx.get("n"))

    groups_txt = ", ".join(groups or [])

    top = []
    top.append(
        f'<div class="profile-top">'
        f'<div class="callsign">{_h(callsign)}</div>'
        f'<div class="profile-right">'
        f'{_pill(team, "team") if team else ""}'
        f'</div>'
        f'</div>'
    )

    chips = []
    if battalion_fal and battalion:
        chips.append(_pill(f"{battalion_fal} ({battalion})", "unit"))
    elif battalion_fal:
        chips.append(_pill(battalion_fal, "unit"))
    elif battalion:
        chips.append(_pill(f"{battalion} HVBAT", "unit"))

    if company:
        chips.append(_pill(f"Company {company}", "unit"))
    if platoon:
        chips.append(_pill(f"Platoon {platoon}", "unit"))
    if group:
        chips.append(_pill(f"Group {group}", "unit"))
    if n:
        chips.append(_pill(f"N {n}", "meta"))

    if chips:
        top.append(f'<div class="chips">{"".join(chips)}</div>')

    rows = []
    rows.append(
        f'<div class="row"><b>Username</b>: '
        f'<code id="taks_username">{_h(_safe(username))}</code> '
        f'<button class="btn" onclick="copyId(\'taks_username\')">Copy</button></div>'
    )

    if atak_role:
        rows.append(f'<div class="row"><b>Role</b>: <code>{_h(atak_role)}</code></div>')

    if remarks:
        rows.append(f'<div class="row"><b>Remarks</b>: <code>{_h(remarks)}</code></div>')

    if groups_txt:
        rows.append(f'<div class="row"><b>Groups</b>: <code>{_h(groups_txt)}</code></div>')

    rows = [r for r in rows if r]
    return '<div class="note">' + "".join(top) + "<hr/>" + "".join(rows) + "</div>"


def _pw_block(*, username: str, ident, reveal_password: bool) -> str:
    if ident is None:
        return """
<div class="note">
  Password: <b>unknown</b> (no TAKS identity record)<br/>
  If created in Marti UI, TAKS does not know the password.
</div>
"""

    origin = _get(ident, "origin", "marti")
    pw_known = bool(_get(ident, "password_known", False))
    pw_val = _get(ident, "password", None) if pw_known else None

    if not pw_known or origin != "taks":
        return f"""
<div class="note">
  Password: <b>unknown</b> (origin={_h(_safe(origin))})<br/>
  This user appears created outside TAKS. Ask admin for out-of-band password or reset.
</div>
"""

    if not reveal_password:
        return f"""
<div class="note">
  Username: <code id="taks_username2">{_h(_safe(username))}</code>
  <button class="btn" onclick="copyId('taks_username2')">Copy</button><br/>
  Password: <b>hidden</b> (admin chose out-of-band)
</div>
"""

    return f"""
<div class="note">
  Username: <code id="taks_username2">{_h(_safe(username))}</code>
  <button class="btn" onclick="copyId('taks_username2')">Copy</button><br/>
  Password: <code id="taks_password">{_h(_safe(pw_val))}</code>
  <button class="btn" onclick="copyId('taks_password')">Copy</button>
</div>
"""


def _lifecycle_card_block(lifecycle: dict | None) -> str:
    """
    Dedicated lifecycle card with evidence (compact, date-heavy).
    Expects lifecycle shape:
      { "stage": "...", "label": "...", "evidence": {...} }
    """
    if not isinstance(lifecycle, dict) or not lifecycle:
        return '<div class="note">No lifecycle data.</div>'

    stage = _norm(lifecycle.get("stage"))
    label = _norm(lifecycle.get("label"))
    ev = lifecycle.get("evidence") or {}
    if not isinstance(ev, dict):
        ev = {}

    # headline
    headline = stage or ""
    if label:
        headline = f"{headline} — {label}" if headline else label
    if not headline:
        headline = "Lifecycle"

    parts: list[str] = []
    parts.append(f'<div class="note"><div class="row"><b>Stage gate</b>: <code>{_h(headline)}</code></div>')

    # TAKS / onboarding facts
    taks_origin = _norm(ev.get("taks_origin"))
    taks_pw_known = bool(ev.get("taks_password_known"))
    onboarding_status = _norm(ev.get("onboarding_status"))
    offboarded = bool(ev.get("offboarded"))

    small = []
    if taks_origin:
        small.append(_row("TAKS origin", _code(taks_origin)))
    if onboarding_status:
        small.append(_row("Onboarding status", _code(onboarding_status)))
    small.append(_row("Password known", _boolpill(taks_pw_known)))
    small.append(_row("Offboarded", _boolpill(offboarded)))

    small = [s for s in small if s]
    if small:
        parts.append('<hr/>')
        parts.extend(small)

    # CoT evidence (if present)
    cot_seen = bool(ev.get("cot_seen"))
    seen_recently = bool(ev.get("seen_recently"))
    act = ev.get("activity")  # not currently set by service, but keep forward-compatible
    if not isinstance(act, dict):
        act = {}

    # In current implementation we only have booleans in evidence, but include fields if present.
    cot_last = act.get("last_cot_time") or ev.get("last_cot_time")
    cot_stale = act.get("stale") or ev.get("stale")
    cot_uid = act.get("uid") or ev.get("cot_uid")
    cot_callsign = act.get("callsign") or ev.get("cot_callsign")
    cot_age = act.get("age_human") or ev.get("age_human")
    cot_is_current = act.get("is_current") if "is_current" in act else ev.get("is_current")

    cot_rows = []
    cot_rows.append(_row("CoT seen", _boolpill(cot_seen)))
    cot_rows.append(_row("Seen recently", _boolpill(seen_recently)))
    if cot_callsign:
        cot_rows.append(_row("CoT callsign", _code(cot_callsign)))
    if cot_uid:
        cot_rows.append(_row("CoT uid", _code(cot_uid)))
    if cot_last:
        cot_rows.append(_row("Last CoT", _fmt_dt(cot_last)))
    if cot_stale:
        cot_rows.append(_row("Stale", _fmt_dt(cot_stale)))
    if cot_age:
        cot_rows.append(_row("Age", _code(cot_age)))
    if cot_is_current is not None:
        cot_rows.append(_row("Is current", _boolpill(bool(cot_is_current))))

    cot_rows = [r for r in cot_rows if r]
    if cot_rows:
        parts.append('<hr/>')
        parts.append('<div class="row"><b>CoT</b>: <span class="muted">presence / timing</span></div>')
        parts.extend(cot_rows)

    # Marti evidence (from service.py: marti_client is already compact)
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
    m_rows.append(_row("Has endpoint", _boolpill(bool(marti.get("has_endpoint")))))
    m_rows.append(_row("Has endpoint event", _boolpill(bool(marti.get("has_endpoint_event")))))
    m_rows.append(_row("Has certificate", _boolpill(bool(marti.get("has_certificate")))))
    if marti.get("endpoints_n") is not None:
        m_rows.append(_row("Endpoints", _code(marti.get("endpoints_n"))))
    if marti.get("certs_by_user_dn_n") is not None:
        m_rows.append(_row("Certs by user_dn", _code(marti.get("certs_by_user_dn_n"))))
    if marti.get("certs_by_client_uid_n") is not None:
        m_rows.append(_row("Certs by client_uid", _code(marti.get("certs_by_client_uid_n"))))
    if marti.get("certs_revoked_n") is not None:
        m_rows.append(_row("Certs revoked", _code(marti.get("certs_revoked_n"))))

    # latest endpoint summary
    if latest_ep:
        ep_bits = []
        if latest_ep.get("callsign"):
            ep_bits.append(f"callsign={_norm(latest_ep.get('callsign'))}")
        if latest_ep.get("uid"):
            ep_bits.append(f"uid={_norm(latest_ep.get('uid'))}")
        if latest_ep.get("id") is not None:
            ep_bits.append(f"id={_norm(latest_ep.get('id'))}")
        if ep_bits:
            m_rows.append(_row("Latest endpoint", _code(", ".join(ep_bits))))

    # latest event summary
    if latest_evt:
        evt_bits = []
        if latest_evt.get("created_ts"):
            evt_bits.append(f"ts={_norm(latest_evt.get('created_ts'))}")
        if latest_evt.get("client_version"):
            evt_bits.append(f"ver={_norm(latest_evt.get('client_version'))}")
        if latest_evt.get("connection_event_type_id") is not None:
            evt_bits.append(f"type={_norm(latest_evt.get('connection_event_type_id'))}")
        if latest_evt.get("client_endpoint_id") is not None:
            evt_bits.append(f"ep_id={_norm(latest_evt.get('client_endpoint_id'))}")
        if latest_evt.get("id") is not None:
            evt_bits.append(f"id={_norm(latest_evt.get('id'))}")
        if evt_bits:
            m_rows.append(_row("Latest endpoint event", _code(", ".join(evt_bits))))

    # latest cert summary
    if latest_cert:
        cert_bits = []
        if latest_cert.get("client_uid"):
            cert_bits.append(f"uid={_norm(latest_cert.get('client_uid'))}")
        if latest_cert.get("issuance_date"):
            cert_bits.append(f"issued={_norm(latest_cert.get('issuance_date'))}")
        if latest_cert.get("effective_date"):
            cert_bits.append(f"eff={_norm(latest_cert.get('effective_date'))}")
        if latest_cert.get("expiration_date"):
            cert_bits.append(f"exp={_norm(latest_cert.get('expiration_date'))}")
        if latest_cert.get("revocation_date"):
            cert_bits.append(f"revoked={_norm(latest_cert.get('revocation_date'))}")
        if cert_bits:
            m_rows.append(_row("Latest certificate", _code(", ".join(cert_bits))))

    m_rows = [r for r in m_rows if r]
    if m_rows:
        parts.append('<hr/>')
        parts.append('<div class="row"><b>Marti</b>: <span class="muted">endpoints / events / certs</span></div>')
        parts.extend(m_rows)

    # Artifacts evidence
    art = ev.get("artifacts") or {}
    if not isinstance(art, dict):
        art = {}

    a_rows = []
    if "present" in art:
        a_rows.append(_row("Artifacts present", _boolpill(bool(art.get("present")))))
    if art.get("artifacts_root"):
        a_rows.append(_row("Artifacts path", _code(art.get("artifacts_root"))))
    if "atak_package_zip" in art:
        a_rows.append(_row("ATAK package.zip", _boolpill(bool(art.get("atak_package_zip")))))
    if "atak_package_creds_zip" in art:
        a_rows.append(_row("ATAK package-creds.zip", _boolpill(bool(art.get("atak_package_creds_zip")))))
    if "any_qr_png" in art:
        a_rows.append(_row("Any QR png", _boolpill(bool(art.get("any_qr_png")))))

    a_rows = [r for r in a_rows if r]
    if a_rows:
        parts.append('<hr/>')
        parts.append('<div class="row"><b>Artifacts</b>: <span class="muted">file evidence only</span></div>')
        parts.extend(a_rows)

    parts.append("</div>")
    return "".join(parts)


def render_soldier_card_page(
    *,
    username: str,
    groups: list[str],
    base: str,
    sel: dict,
    ident=None,
    token: str,
    expires_at_utc: datetime,
    reveal_password: bool,
    lifecycle: dict | None = None,
) -> str:
    bump = int(datetime.now(timezone.utc).timestamp())

    atak_import_qr = f"{base}/api/onboarding/cards/{token}/packages/atak/qr.png?b={bump}"
    atak_import_txt = f"{base}/api/onboarding/cards/{token}/packages/atak/qr.txt?b={bump}"
    atak_pkg = f"{base}/api/onboarding/cards/{token}/packages/atak/package.zip"

    creds_html = _pw_block(username=username, ident=ident, reveal_password=reveal_password)
    profile_html = _profile_block(username=username, groups=groups, sel=sel, ident=ident)
    lifecycle_html = _lifecycle_card_block(lifecycle)

    token_url = f"{base}/api/onboarding/cards/{token}"
    exp = expires_at_utc.replace(microsecond=0).isoformat()

    btn_css = """
    .btn { font-size: 12px; padding: 3px 8px; border: 1px solid rgba(255,255,255,0.20); border-radius: 10px; background: rgba(255,255,255,0.06); color: rgba(255,255,255,0.90); cursor: pointer; }
    .btn:hover { background: rgba(255,255,255,0.10); }
    """

    script_html = """<script>
    function copyText(t) {
      try { navigator.clipboard.writeText(t); } catch (e) {}
    }
    function copyId(id) {
      var el = document.getElementById(id);
      if (!el) return;
      copyText(el.textContent || el.innerText || '');
    }
    </script>"""

    brand_js_html = """<script>
(function () {
  "use strict";

  var BUMP = "__BUMP__";
  var BRAND = "/assets/brand.json?b=" + encodeURIComponent(BUMP);

  function renderBrandLogos() {
    var host = document.getElementById("__brand_logos");
    if (!host) return;
    host.innerHTML = "";

    fetch(BRAND, { cache: "no-store" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (b) {
        if (!b || !b.logos || !b.logos.length) return;

        b.logos.forEach(function (it) {
          if (!it || it.uploaded !== true) return;
          var n = it.n;
          if (!(n >= 1 && n <= 4)) return;

          var img = document.createElement("img");
          img.alt = "logo" + n;

          var ext = (it && it.ext) ? String(it.ext).toLowerCase() : "";
          if (!ext) ext = "svg";

          var base = "/assets/logo" + n + ".";
          img.src = base + ext + "?b=" + encodeURIComponent(BUMP);

          var all = ["svg", "png", "webp", "jpg", "jpeg"];
          var fb = [];
          for (var i = 0; i < all.length; i++) {
            if (all[i] !== ext) fb.push(base + all[i] + "?b=" + encodeURIComponent(BUMP));
          }
          img.dataset.fallback = fb.join(",");
          img.onerror = function () {
            var f = (this.dataset.fallback || "").split(",");
            if (f.length && f[0]) {
              this.src = f.shift();
              this.dataset.fallback = f.join(",");
            } else {
              this.style.display = "none";
            }
          };

          host.appendChild(img);
        });
      })
      .catch(function () { /* ignore */ });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", renderBrandLogos);
  } else {
    renderBrandLogos();
  }
})();
</script>""".replace("__BUMP__", str(bump))

    style_html = """<style>
:root {
  --bg0: #0b0c10;
  --bg1: #101218;
  --card: rgba(255,255,255,0.04);
  --card2: rgba(255,255,255,0.06);
  --bd: rgba(255,255,255,0.10);
  --txt: rgba(255,255,255,0.92);
  --muted: rgba(255,255,255,0.65);
  --link: #8bb8ff;
}

body {
  font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;
  margin: 22px;
  color: var(--txt);
  background:
    radial-gradient(1200px 500px at 30% 0%, rgba(255,255,255,0.06), transparent 60%),
    radial-gradient(900px 450px at 80% 30%, rgba(255,255,255,0.04), transparent 55%),
    linear-gradient(180deg, var(--bg0), var(--bg1));
  min-height: 100vh;
}

.topbar { display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; margin-bottom: 12px; gap: 14px; }
.brand { display:flex; align-items:center; gap: 10px; flex-wrap:wrap; }
.taksmark img { height: 26px; width: auto; display:block; filter: drop-shadow(0 6px 18px rgba(0,0,0,0.55)); }
.brandchain-row { display:flex; align-items:center; gap: 10px; flex-wrap:wrap; }
.brandchain-row img { height: 24px; width: auto; max-width: 260px; object-fit: contain; display:block; filter: drop-shadow(0 2px 10px rgba(0,0,0,0.45)); }

.title { font-size: 20px; font-weight: 850; letter-spacing: 0.2px; }
.hdr { display:flex; justify-content:space-between; gap:12px; flex-wrap:wrap; margin-bottom: 12px; }
.meta { font-size: 12px; color: var(--muted); line-height: 1.35; }
.muted { color: var(--muted); font-size: 12px; }

.grid { display:grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 12px; }

.card {
  border: 1px solid var(--bd);
  background: var(--card);
  border-radius: 16px;
  padding: 14px;
  box-shadow: 0 18px 40px rgba(0,0,0,0.35);
}

.note {
  border: 1px solid var(--bd);
  background: var(--card2);
  border-radius: 14px;
  padding: 12px;
  line-height: 1.5;
}

.note hr { border: none; border-top: 1px solid rgba(255,255,255,0.10); margin: 10px 0; }

a { color: var(--link); text-decoration: none; }
a:hover { text-decoration: underline; }

.qr { display:flex; justify-content:center; align-items:center; padding: 10px; background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08); border-radius: 14px; }
.qr img { width: 100%; max-width: 360px; height: auto; display:block; border-radius: 10px; background: #fff; }

code { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; background: rgba(0,0,0,0.28); border: 1px solid rgba(255,255,255,0.10); border-radius: 8px; padding: 2px 6px; }

.profile-top { display:flex; justify-content:space-between; align-items:flex-start; gap: 10px; }
.callsign { font-size: 18px; font-weight: 950; letter-spacing: 0.02em; }
.profile-right { display:flex; gap: 8px; align-items:center; justify-content:flex-end; flex-wrap:wrap; }

.chips { margin-top: 8px; display:flex; flex-wrap:wrap; gap: 6px; }

.pill {
  display:inline-flex;
  align-items:center;
  gap: 6px;
  padding: 4px 9px;
  border-radius: 999px;
  border: 1px solid rgba(255,255,255,0.14);
  background: rgba(0,0,0,0.22);
  color: rgba(255,255,255,0.86);
  font-size: 12px;
  font-weight: 750;
  letter-spacing: 0.02em;
}
.pill.team { background: rgba(255,255,255,0.08); }

.row { margin-top: 6px; }
.row b { color: rgba(255,255,255,0.78); font-weight: 800; }
</style>"""

    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Soldier Card for {_h(_safe(username))}</title>
{style_html}
<style>{btn_css}</style>
</head>
<body>
  <div class="topbar">
    <div class="brand">
      <span class="taksmark"><img alt="TAKS" src="/assets/taks-logo.svg?b={bump}"/></span>
      <span class="brandchain-row" id="__brand_logos"></span>
    </div>
    <div class="meta">
      Expires: <code>{_h(_safe(exp))}</code><br/>
      Token URL: <code id="taks_token_url">{_h(_safe(token_url))}</code>
      <button class="btn" onclick="copyId('taks_token_url')">Copy</button>
    </div>
  </div>

  <div class="hdr">
    <div class="title">Soldier Card</div>
  </div>

  <div class="grid">
    <div class="card">
      <h3>ATAK – Import package</h3>
      <div class="note">
        1) Scan QR to import server + identity defaults<br/>
        2) Enter credentials (if provided)<br/>
        3) Connect
      </div>
      <div class="qr"><img alt="ATAK Import QR" src="{atak_import_qr}" /></div>
      <div class="meta" style="margin-top:10px;">
        QR payload: <a href="{atak_import_txt}">qr.txt</a><br/>
        Package: <a href="{atak_pkg}">{_h(_safe(atak_pkg))}</a><br/>
        After import: <code>ATAK → Settings → TAK Server → (server) → Username/Password</code>
      </div>
    </div>

    <div class="card">
      <h3>Profile</h3>
      {profile_html}
    </div>

    <div class="card">
      <h3>Lifecycle</h3>
      {lifecycle_html}
    </div>

    <div class="card">
      <h3>Credentials</h3>
      {creds_html}
    </div>
  </div>

{script_html}
{brand_js_html}
</body></html>"""
