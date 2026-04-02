from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from html import escape as h

from takctl.onboarding.soldier_card.blocks import lifecycle_block, password_block, profile_block
from takctl.onboarding.soldier_card.i18n import lang_norm, t
from takctl.config import load_config
from takctl.onboarding.atak import _read_runtime_ca_password, _read_runtime_user_cert_password


def _cfg_bool(cfg, key: str, default: bool = False) -> bool:
    try:
        v = getattr(cfg, key)
    except Exception:
        try:
            v = (getattr(cfg, "values", {}) or {}).get(key)
        except Exception:
            v = None
    if v is None:
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "y", "on")


def _cfg_str(cfg, key: str, default: str = "") -> str:
    try:
        v = getattr(cfg, key)
    except Exception:
        try:
            v = (getattr(cfg, "values", {}) or {}).get(key)
        except Exception:
            v = None
    if v is None:
        return default
    return str(v).strip()


def _onboarding_mode(cfg) -> str:
    raw = _cfg_str(cfg, "onboarding_mode", "").lower()
    if raw in ("auto-enroll", "cert-creation"):
        return raw
    return "cert-creation" if _cfg_bool(cfg, "create_cert_with_user", True) else "auto-enroll"


def _read_user_client_password(username: str) -> str:
    u = (username or "").strip()
    if not u:
        return ""
    for p in (
        Path("/opt/tak/certs/files/04_USERS") / u / ".client-password",
        Path("/opt/tak/takctl-state/onboarding/identities") / f"{u}.client-password",
    ):
        try:
            v = p.read_text(encoding="utf-8", errors="replace").strip()
            if v:
                return v
        except Exception:
            pass
    return ""


def _card_bool(cfg, key: str, default: bool) -> bool:
    return _cfg_bool(cfg, key, default)


def render_soldier_card_page(
    *,
    lang: str | None,
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
    l = lang_norm(lang)

    cfg = load_config()
    onboarding_mode = _onboarding_mode(cfg)
    create_cert_with_user = (onboarding_mode == "cert-creation")

    soft_cert_include_client_password = _cfg_bool(cfg, "soft_cert_include_client_password", False)
    soft_cert_include_truststore_password = _cfg_bool(cfg, "soft_cert_include_truststore_password", False)
    reveal_truststore_password_on_soldier_card = _cfg_bool(cfg, "reveal_truststore_password_on_soldier_card", False)
    reveal_client_password_on_soldier_card = _cfg_bool(cfg, "reveal_client_password_on_soldier_card", False)

    atak_qr_quick_connect_enabled = _card_bool(cfg, "atak_qr_quick_connect_enabled", True)
    atak_qr_auto_enroll_zip_enabled = _card_bool(cfg, "atak_qr_auto_enroll_zip_enabled", True)
    atak_qr_soft_cert_zip_enabled = _card_bool(cfg, "atak_qr_soft_cert_zip_enabled", True)

    itak_qr_quick_connect_enabled = _card_bool(cfg, "itak_qr_quick_connect_enabled", True)
    itak_soft_cert_zip_enabled = _card_bool(cfg, "itak_soft_cert_zip_enabled", True)
    itak_manual_import_warning_enabled = _card_bool(cfg, "itak_manual_import_warning_enabled", True)

    atak_qr_quick_connect_png = f"{base}/api/onboarding/cards/{token}/packages/atak/quick-connect/qr.png?b={bump}"
    atak_qr_quick_connect_txt = f"{base}/api/onboarding/cards/{token}/packages/atak/quick-connect/qr.txt?b={bump}"

    atak_qr_auto_enroll_png = f"{base}/api/onboarding/cards/{token}/packages/atak/auto-enroll/qr.png?b={bump}"
    atak_qr_auto_enroll_txt = f"{base}/api/onboarding/cards/{token}/packages/atak/auto-enroll/qr.txt?b={bump}"
    atak_auto_enroll_zip = f"{base}/api/onboarding/cards/{token}/packages/atak/auto-enroll/package.zip"

    atak_qr_soft_cert_png = f"{base}/api/onboarding/cards/{token}/packages/atak/soft-cert/qr.png?b={bump}"
    atak_qr_soft_cert_txt = f"{base}/api/onboarding/cards/{token}/packages/atak/soft-cert/qr.txt?b={bump}"
    atak_soft_cert_zip = f"{base}/api/onboarding/cards/{token}/packages/atak/soft-cert/package.zip"

    itak_qr_quick_connect_png = f"{base}/api/onboarding/cards/{token}/packages/itak/quick-connect/qr.png?b={bump}"
    itak_qr_quick_connect_txt = f"{base}/api/onboarding/cards/{token}/packages/itak/quick-connect/qr.txt?b={bump}"
    itak_soft_cert_zip = f"{base}/api/onboarding/cards/{token}/packages/itak/soft-cert/package.zip"

    browser_card_qr = f"{base}/api/onboarding/cards/{token}/card-url/qr.png?b={bump}"
    browser_card_txt = f"{base}/api/onboarding/cards/{token}/card-url/qr.txt?b={bump}"

    profile_html = profile_block(lang=l, username=username, groups=groups, sel=sel, ident=ident)
    lifecycle_html = lifecycle_block(l, lifecycle)

    truststore_password = None
    client_password = None
    if create_cert_with_user and (not soft_cert_include_truststore_password) and reveal_truststore_password_on_soldier_card:
        truststore_password = _read_runtime_ca_password() or None
    if create_cert_with_user and (not soft_cert_include_client_password) and reveal_client_password_on_soldier_card:
        client_password = _read_user_client_password(username) or _read_runtime_user_cert_password() or None

    creds_html = password_block(
        lang=l,
        username=username,
        ident=ident,
        reveal_password=reveal_password,
        truststore_password=truststore_password,
        client_password=client_password,
    )

    if create_cert_with_user:
        mode_label = "soft-cert / cert-creation"
        mode_summary_html = (
            f'<div class="meta" style="margin-top:8px;">'
            f'Mode: <code>{h(mode_label)}</code> · '
            f'client password embedded: <code>{"yes" if soft_cert_include_client_password else "no"}</code> · '
            f'trust password embedded: <code>{"yes" if soft_cert_include_truststore_password else "no"}</code>'
            f"</div>"
        )
    else:
        mode_label = "auto-enroll / quick connect"
        mode_summary_html = (
            f'<div class="meta" style="margin-top:8px;">'
            f'Mode: <code>{h(mode_label)}</code> · '
            f'user/password onboarding'
            f"</div>"
        )

    token_url = f"{base}/api/onboarding/cards/{token}"
    exp = expires_at_utc.replace(microsecond=0).isoformat()

    btn_css = """
    .btn { font-size: 12px; padding: 7px 11px; border: 1px solid rgba(255,255,255,0.20); border-radius: 12px; background: rgba(255,255,255,0.06); color: rgba(255,255,255,0.92); cursor: pointer; text-decoration:none; display:inline-block; font-weight:600; }
    .btn:hover { background: rgba(255,255,255,0.10); }
    .warn { color:#ffd27a; }
    .danger-note { margin-top:8px; padding:10px 12px; border-radius:10px; background:rgba(255,210,122,0.08); border:1px solid rgba(255,210,122,0.18); color:#ffe3ac; font-size:13px; line-height:1.45; }
    .stepcard { background: rgba(255,255,255,0.04); border:1px solid rgba(255,255,255,0.08); border-radius:16px; padding:16px; }
    .stepcard h4 { margin:0 0 8px 0; font-size:15px; }
    .qrimg { width:220px; max-width:100%; height:auto; border-radius:12px; background:#fff; padding:8px; }
    .choicegrid { display:grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap:14px; }
    .guidegrid { display:grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap:14px; }
    .infogrid { display:grid; grid-template-columns: 1fr; gap:14px; }
    .dlrow { display:flex; gap:8px; flex-wrap:wrap; margin-top:10px; }
    code.inline { font-size:12px; }
    .hero { background: linear-gradient(180deg, rgba(255,255,255,0.05), rgba(255,255,255,0.03)); border:1px solid rgba(255,255,255,0.10); border-radius:18px; padding:18px 20px; margin-bottom:14px; box-shadow: 0 10px 30px rgba(0,0,0,0.22); }
    .eyebrow { font-size:12px; letter-spacing:0.14em; text-transform:uppercase; color:#8bb8ff; font-weight:700; }
    .hero-title { font-size:30px; line-height:1.1; font-weight:850; margin-top:10px; }
    .hero-sub { font-size:15px; line-height:1.6; color:rgba(255,255,255,0.78); margin-top:10px; max-width:760px; }
    .slogan { margin-top:8px; font-size:12px; letter-spacing:0.12em; text-transform:uppercase; color:rgba(255,255,255,0.58); }
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
    function showMainTab(id) {
      var ids = ["start", "guide", "info", "advanced"];
      for (var i = 0; i < ids.length; i++) {
        var panel = document.getElementById("tab_" + ids[i]);
        var btn = document.getElementById("tabbtn_" + ids[i]);
        var active = (ids[i] === id);
        if (panel) panel.style.display = active ? "block" : "none";
        if (btn) {
          if (active) btn.classList.add("choicebtn-active");
          else btn.classList.remove("choicebtn-active");
        }
      }
    }
    function showFlow(id) {
      var ids = ["android", "iphone", "browser"];
      for (var i = 0; i < ids.length; i++) {
        var flow = document.getElementById("flow_" + ids[i]);
        var btn = document.getElementById("btn_" + ids[i]);
        var active = (ids[i] === id);
        if (flow) flow.style.display = active ? "block" : "none";
        if (btn) {
          if (active) btn.classList.add("choicebtn-active");
          else btn.classList.remove("choicebtn-active");
        }
      }
    }
    document.addEventListener("DOMContentLoaded", function () {
      showMainTab("start");
      showFlow("android");
    });
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
      .catch(function () {});
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
.meta { font-size: 12px; color: var(--muted); line-height: 1.35; }
.muted { color: var(--muted); font-size: 12px; }
.card { background: var(--card); border: 1px solid var(--bd); border-radius: 16px; padding: 16px; box-shadow: 0 10px 30px rgba(0,0,0,0.22); }
.tabs { display:flex; gap:8px; flex-wrap:wrap; margin-bottom:12px; }
.choicebtn { border:1px solid var(--bd); background:var(--card2); color:var(--txt); padding:8px 12px; border-radius:999px; cursor:pointer; font-size:13px; }
.choicebtn-active { outline:2px solid rgba(139,184,255,0.45); }
a { color: var(--link); }
pre { white-space: pre-wrap; word-break: break-word; }
</style>"""

    android_cards = []

    if atak_qr_quick_connect_enabled:
        android_cards.append(f"""
        <div class="stepcard">
          <h4>ATAK quick-connect QR</h4>
          <div class="muted">Android kamera -> tak:// -> ATAK auto-enroll med användarnamn/lösenord.</div>
          <div style="margin-top:10px;"><img class="qrimg" src="{h(atak_qr_quick_connect_png)}" alt="ATAK quick-connect QR"/></div>
          <div class="dlrow">
            <a class="btn" href="{h(atak_qr_quick_connect_png)}">{h(t(l, "soldier.open_qr"))}</a>
            <a class="btn" href="{h(atak_qr_quick_connect_txt)}">{h(t(l, "soldier.open_text"))}</a>
          </div>
        </div>
        """)

    if atak_qr_auto_enroll_zip_enabled:
        android_cards.append(f"""
        <div class="stepcard">
          <h4>ATAK auto-enroll zip</h4>
          <div class="muted">QR -> ladda ner ATAK-paket för auto-enroll.</div>
          <div style="margin-top:10px;"><img class="qrimg" src="{h(atak_qr_auto_enroll_png)}" alt="ATAK auto-enroll zip QR"/></div>
          <div class="dlrow">
            <a class="btn" href="{h(atak_auto_enroll_zip)}">Download zip</a>
            <a class="btn" href="{h(atak_qr_auto_enroll_png)}">{h(t(l, "soldier.open_qr"))}</a>
            <a class="btn" href="{h(atak_qr_auto_enroll_txt)}">{h(t(l, "soldier.open_text"))}</a>
          </div>
        </div>
        """)

    if atak_qr_soft_cert_zip_enabled:
        android_cards.append(f"""
        <div class="stepcard">
          <h4>ATAK soft-cert zip</h4>
          <div class="muted">QR -> ladda ner ATAK-paket med certifikat.</div>
          <div style="margin-top:10px;"><img class="qrimg" src="{h(atak_qr_soft_cert_png)}" alt="ATAK soft-cert zip QR"/></div>
          <div class="dlrow">
            <a class="btn" href="{h(atak_soft_cert_zip)}">Download zip</a>
            <a class="btn" href="{h(atak_qr_soft_cert_png)}">{h(t(l, "soldier.open_qr"))}</a>
            <a class="btn" href="{h(atak_qr_soft_cert_txt)}">{h(t(l, "soldier.open_text"))}</a>
          </div>
        </div>
        """)

    iphone_cards = []

    if itak_qr_quick_connect_enabled:
        warn = ""
        if itak_manual_import_warning_enabled:
            warn = """
            <div class="danger-note">
              This is currently not working reliably.
              Download the zip-file manually and install it using
              <strong>Upload server package</strong> in the iTAK config menu
              (<strong>Networking -&gt; Servers -&gt; +</strong>).
            </div>
            """
        iphone_cards.append(f"""
        <div class="stepcard">
          <h4>iTAK quick-connect QR</h4>
          <div class="muted">iTAK:s enda QR-spår. Behålls för felsökning, men manuell zip-install rekommenderas just nu.</div>
          <div style="margin-top:10px;"><img class="qrimg" src="{h(itak_qr_quick_connect_png)}" alt="iTAK quick-connect QR"/></div>
          <div class="dlrow">
            <a class="btn" href="{h(itak_qr_quick_connect_png)}">{h(t(l, "soldier.open_qr"))}</a>
            <a class="btn" href="{h(itak_qr_quick_connect_txt)}">{h(t(l, "soldier.open_text"))}</a>
          </div>
          {warn}
        </div>
        """)

    if itak_soft_cert_zip_enabled:
        iphone_cards.append(f"""
        <div class="stepcard">
          <h4>iTAK soft-cert zip</h4>
          <div class="muted">Ladda ner zip-filen manuellt och installera via Upload server package.</div>
          <div class="dlrow" style="margin-top:12px;">
            <a class="btn" href="{h(itak_soft_cert_zip)}">Download zip</a>
          </div>
        </div>
        """)

    android_html = '<div class="choicegrid">' + "".join(android_cards or ['<div class="muted">ATAK artifacts disabled in config.</div>']) + '</div>'
    iphone_html = '<div class="choicegrid">' + "".join(iphone_cards or ['<div class="muted">iTAK artifacts disabled in config.</div>']) + '</div>'

    browser_html = f"""
    <div class="choicegrid">
      <div class="stepcard">
        <h4>{h(t(l, "soldier.browser_card"))}</h4>
        <div class="muted">{h(t(l, "soldier.browser_card_desc"))}</div>
        <div style="margin-top:10px;"><img class="qrimg" src="{h(browser_card_qr)}" alt="Card URL QR"/></div>
        <div class="dlrow">
          <a class="btn" href="{h(token_url)}">{h(t(l, "soldier.open_card"))}</a>
          <a class="btn" href="{h(browser_card_qr)}">{h(t(l, "soldier.open_qr"))}</a>
          <a class="btn" href="{h(browser_card_txt)}">{h(t(l, "soldier.open_text"))}</a>
        </div>
      </div>
    </div>
    """

    guide_html = f"""
    <div class="stepcard" style="margin-bottom:14px;">
      <div class="muted">{h(t(l, "soldier.guide_intro"))}</div>
    </div>
    <div class="guidegrid">
      <div class="stepcard">
        <h4>{h(t(l, "soldier.guide.step1.title"))}</h4>
        <div class="muted">{h(t(l, "soldier.guide.step1.body"))}</div>
      </div>
      <div class="stepcard">
        <h4>{h(t(l, "soldier.guide.step2.title"))}</h4>
        <div class="muted">{h(t(l, "soldier.guide.step2.body"))}</div>
      </div>
      <div class="stepcard">
        <h4>{h(t(l, "soldier.guide.step3.title"))}</h4>
        <div class="muted">{h(t(l, "soldier.guide.step3.body"))}</div>
      </div>
      <div class="stepcard">
        <h4>{h(t(l, "soldier.guide.step4.title"))}</h4>
        <div class="muted">{h(t(l, "soldier.guide.step4.body"))}</div>
      </div>
    </div>
    """

    info_html = f"""
    <div class="infogrid">
      <div class="stepcard">
        <h4>{h(t(l, "soldier.info_title"))}</h4>
        <div style="margin-top:12px;">{profile_html}</div>
      </div>
      <div class="stepcard">{creds_html}</div>
      <div class="stepcard">{lifecycle_html}</div>
    </div>
    """

    brand_slogan = ""
    try:
        brand_slogan = _cfg_str(cfg, "site_slogan", "")
    except Exception:
        brand_slogan = ""
    if not brand_slogan:
        try:
            brand_slogan = json.loads(Path("/opt/tak/tools/takctl/web/assets/brand.json").read_text(encoding="utf-8")).get("slogan") or ""
        except Exception:
            brand_slogan = ""

    return f"""<!doctype html>
<html lang="{h(l)}">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>{h(t(l, "soldier.title_for", username=username))}</title>
  {style_html}
  <style>{btn_css}</style>
</head>
<body>
  <div class="topbar">
    <div class="brand">
      <div class="taksmark"><img src="/assets/taks-logo.png?b={bump}" alt="TAKS"/></div>
      <div class="brandchain-row" id="__brand_logos"></div>
    </div>
    <div class="meta">
      <div>User: <strong>{h(username)}</strong></div>
      <div>Token expires: <code>{h(exp)}</code></div>
    </div>
  </div>

  <div class="hero">
    <div class="eyebrow">TAKS ONBOARDING</div>
    <div class="hero-title">{h(t(l, "soldier.welcome"))}</div>
    <div class="hero-sub">{h(t(l, "soldier.subtitle"))}</div>
    {f'<div class="slogan">{h(brand_slogan)}</div>' if brand_slogan else ''}
    {mode_summary_html}
  </div>

  <div class="card">
    <div class="tabs">
      <button id="tabbtn_start" class="choicebtn" onclick="showMainTab('start')">{h(t(l, "soldier.start"))}</button>
      <button id="tabbtn_guide" class="choicebtn" onclick="showMainTab('guide')">{h(t(l, "soldier.guide"))}</button>
      <button id="tabbtn_info" class="choicebtn" onclick="showMainTab('info')">{h(t(l, "soldier.info_tab"))}</button>
      <button id="tabbtn_advanced" class="choicebtn" onclick="showMainTab('advanced')">{h(t(l, "soldier.advanced_tab"))}</button>
    </div>

    <div id="tab_start">
      <div class="tabs" style="margin-top:6px;">
        <button id="btn_android" class="choicebtn" onclick="showFlow('android')">{h(t(l, "soldier.android"))}</button>
        <button id="btn_iphone" class="choicebtn" onclick="showFlow('iphone')">{h(t(l, "soldier.iphone"))}</button>
        <button id="btn_browser" class="choicebtn" onclick="showFlow('browser')">{h(t(l, "soldier.browser"))}</button>
      </div>

      <div id="flow_android" style="margin-top:12px;">{android_html}</div>
      <div id="flow_iphone" style="margin-top:12px; display:none;">{iphone_html}</div>
      <div id="flow_browser" style="margin-top:12px; display:none;">{browser_html}</div>
    </div>

    <div id="tab_guide" style="display:none; margin-top:12px;">
      {guide_html}
    </div>

    <div id="tab_info" style="display:none; margin-top:12px;">
      {info_html}
    </div>

    <div id="tab_advanced" style="display:none; margin-top:12px;">
      <div class="stepcard">
        <h4>{h(t(l, "soldier.card_url"))}</h4>
        <div class="muted" id="card_url_txt">{h(token_url)}</div>
        <div class="dlrow">
          <button class="btn" onclick="copyId('card_url_txt')">{h(t(l, "soldier.copy"))}</button>
          <a class="btn" href="{h(token_url)}">{h(t(l, "soldier.open_card"))}</a>
        </div>
      </div>
    </div>
  </div>

  {script_html}
  {brand_js_html}
</body>
</html>
"""


__all__ = ["render_soldier_card_page"]
