from __future__ import annotations

from datetime import datetime, timezone
from html import escape as h

from takctl.onboarding.soldier_card.blocks import lifecycle_block, password_block, profile_block
from takctl.onboarding.soldier_card.i18n import lang_norm, t
from takctl.onboarding.soldier_card.common import safe
from takctl.config import load_config




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

    atak_import_qr = f"{base}/api/onboarding/cards/{token}/packages/atak/qr.png?b={bump}"
    atak_import_txt = f"{base}/api/onboarding/cards/{token}/packages/atak/qr.txt?b={bump}"
    atak_pkg = f"{base}/api/onboarding/cards/{token}/packages/atak/package.zip"

    itak_qr = f"{base}/api/onboarding/cards/{token}/packages/itak/qr.png?b={bump}"
    itak_txt = f"{base}/api/onboarding/cards/{token}/packages/itak/qr.txt?b={bump}"
    itak_pkg = f"{base}/api/onboarding/cards/{token}/packages/itak/package.zip"

    browser_card_qr = f"{base}/api/onboarding/cards/{token}/card-url/qr.png?b={bump}"
    browser_card_txt = f"{base}/api/onboarding/cards/{token}/card-url/qr.txt?b={bump}"

    creds_html = password_block(lang=l, username=username, ident=ident, reveal_password=reveal_password)
    profile_html = profile_block(lang=l, username=username, groups=groups, sel=sel, ident=ident)
    lifecycle_html = lifecycle_block(l, lifecycle)

    cfg = load_config()
    onboarding_mode = _onboarding_mode(cfg)
    create_cert_with_user = (onboarding_mode == "cert-creation")
    include_client_password_in_package = _cfg_bool(cfg, "include_client_password_in_package", False)
    include_truststore_password_in_package = _cfg_bool(cfg, "include_truststore_password_in_package", False)

    needs_manual_import_passwords = create_cert_with_user and (
        (not include_client_password_in_package) or (not include_truststore_password_in_package)
    )
    needs_user_password = not create_cert_with_user

    if create_cert_with_user:
        atak_start_note = """
        1. Öppna telefonens kamera.
        <br/>2. Skanna QR-koden med kameran.
        <br/>3. Öppna länken i ATAK.
        <br/>4. Om det inte fungerar, ladda ned paketet manuellt.
        """
        if needs_manual_import_passwords:
            itak_start_note = """
            1. Öppna iTAK på telefonen.
            <br/>2. Öppna QR-skanning i iTAK.
            <br/>3. Skanna QR-koden i appen, eller ladda ned paketet.
            <br/>4. Om iTAK frågar efter importlösen använder du uppgifterna nedan.
            """
            guide_step4 = """
            Om appen frågar efter importlösen eller certifikat-lösen använder du uppgifterna på detta kort.
            <br/>Om inget lösenord visas här, kontakta instruktör.
            """
        else:
            itak_start_note = """
            1. Öppna iTAK på telefonen.
            <br/>2. Öppna QR-skanning i iTAK.
            <br/>3. Skanna QR-koden i appen, eller ladda ned paketet.
            <br/>4. Följ importen i iTAK.
            """
            guide_step4 = """
            Om appen frågar efter uppgifter använder du uppgifterna på detta kort.
            <br/>Om inget lösenord visas här, kontakta instruktör.
            """
    else:
        atak_start_note = """
        1. Öppna telefonens kamera.
        <br/>2. Skanna QR-koden med kameran.
        <br/>3. Öppna länken i ATAK.
        <br/>4. När ATAK frågar efter användarnamn och lösenord använder du uppgifterna nedan.
        """
        itak_start_note = """
        Denna onboardingmodell är byggd för Android / ATAK auto-enroll.
        <br/>Om du har iPhone behöver du hjälp av instruktör eller annan väg.
        """
        guide_step4 = """
        Om ATAK frågar efter användarnamn och lösenord använder du uppgifterna på detta kort.
        <br/>Om inget lösenord visas här, kontakta instruktör.
        """

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
    function showMainTab(id) {
      var ids = ["start", "guide", "advanced"];
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

.choicebar { display:flex; gap:8px; flex-wrap:wrap; margin: 0 0 12px 0; }
.choicebtn {
  appearance:none; -webkit-appearance:none; -moz-appearance:none;
  padding: 8px 12px; border-radius: 10px; cursor: pointer;
  border: 1px solid rgba(255,255,255,0.16);
  background: rgba(255,255,255,0.05); color: var(--txt);
  font-size: 13px; font-weight: 800;
}
.choicebtn-active { background: rgba(255,255,255,0.14); }
.maintabs { display:flex; gap:8px; flex-wrap:wrap; margin: 0 0 12px 0; }
.maintab { display:none; }
.flow { display:none; }
.flow h3 { margin-top: 0; }
</style>"""

    return f"""<!doctype html>
<html lang="{h(t(l, "soldier.html_lang"))}"><head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{h(t(l, "soldier.title_for", username=safe(username)))}</title>
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
      {h(t(l, "soldier.expires"))}: <code>{h(safe(exp))}</code><br/>
      {h(t(l, "soldier.token_url"))}: <code id="taks_token_url">{h(safe(token_url))}</code>
      <button class="btn" onclick="copyId('taks_token_url')">{h(t(l, "soldier.copy"))}</button>
    </div>
  </div>

  <div class="hdr">
    <div class="title">{h(t(l, "soldier.title"))}</div>
  </div>

  <div class="maintabs">
    <button id="tabbtn_start" class="choicebtn" type="button" onclick="showMainTab('start')">Start</button>
    <button id="tabbtn_guide" class="choicebtn" type="button" onclick="showMainTab('guide')">Guide</button>
    <button id="tabbtn_advanced" class="choicebtn" type="button" onclick="showMainTab('advanced')">Avancerat</button>
  </div>

  <div id="tab_start" class="maintab">
    <div class="note" style="margin-bottom:12px;">
      Börja här. Välj den telefon eller väg som passar dig bäst.
    </div>

    <div class="choicebar">
      <button id="btn_android" class="choicebtn" type="button" onclick="showFlow('android')">Android / ATAK</button>
      <button id="btn_iphone" class="choicebtn" type="button" onclick="showFlow('iphone')">iPhone / iTAK</button>
      <button id="btn_browser" class="choicebtn" type="button" onclick="showFlow('browser')">Öppna i browser</button>
    </div>

    <div id="flow_android" class="card flow">
      <h3>Android / ATAK</h3>
      <div class="note">
        {atak_start_note}
      </div>
      <div class="qr"><img alt="ATAK Import QR" src="{atak_import_qr}" /></div>
      <div class="meta" style="margin-top:10px;">
        Ladda ned paket: <a href="{atak_pkg}">{h(safe(atak_pkg))}</a>
      </div>
    </div>

    <div id="flow_iphone" class="card flow">
      <h3>iPhone / iTAK</h3>
      <div class="note">
        {itak_start_note}
      </div>
      <div class="qr"><img alt="iTAK QR" src="{itak_qr}" /></div>
      <div class="meta" style="margin-top:10px;">
        Ladda ned paket: <a href="{itak_pkg}">{h(safe(itak_pkg))}</a>
      </div>
    </div>

    <div id="flow_browser" class="card flow">
      <h3>Öppna i browser</h3>
      <div class="note">
        Använd detta om du först vill öppna soldatkortet i telefonens browser.
        <br/>Bra som fallback om QR-import i appen inte fungerar direkt.
      </div>
      <div class="qr"><img alt="Soldier Card URL QR" src="{browser_card_qr}" /></div>
      <div class="meta" style="margin-top:10px;">
        Direktlänk: <code>{h(safe(token_url))}</code>
      </div>
    </div>

    <div class="grid" style="margin-top:12px;">
      <div class="card">
        <h3>{h(t(l, "soldier.credentials"))}</h3>
        {creds_html}
      </div>
    </div>
  </div>

  <div id="tab_guide" class="maintab">
    <div class="grid">
      <div class="card">
        <h3>Steg 1 — Välj rätt väg</h3>
        <div class="note">
          Har du Android väljer du Android / ATAK.
          <br/>Har du iPhone väljer du iPhone / iTAK.
          <br/>Fungerar inget annat kan du öppna kortet i browsern först.
        </div>
      </div>

      <div class="card">
        <h3>Steg 2 — Öppna rätt app</h3>
        <div class="note">
          Android / ATAK: använd telefonens kamera för att öppna QR-koden i ATAK.
          <br/>iPhone / iTAK: öppna iTAK och använd QR-skanning i appen.
        </div>
      </div>

      <div class="card">
        <h3>Steg 3 — Skanna koden</h3>
        <div class="note">
          ATAK: skanna med telefonens kamera.
          <br/>iTAK: skanna i iTAK-appen.
          <br/>Om det inte fungerar, använd nedladdningslänken i Start-fliken.
        </div>
      </div>

      <div class="card">
        <h3>Steg 4 — Använd uppgifterna om appen frågar</h3>
        <div class="note">
          {guide_step4}
        </div>
      </div>
    </div>
  </div>

  <div id="tab_advanced" class="maintab">
    <div class="grid">
      <div class="card">
        <h3>{h(t(l, "soldier.profile"))}</h3>
        {profile_html}
      </div>

      <div class="card">
        <h3>{h(t(l, "soldier.lifecycle"))}</h3>
        {lifecycle_html}
      </div>

      <div class="card">
        <h3>Direktlänkar</h3>
        <div class="meta">
          ATAK QR payload: <a href="{atak_import_txt}">qr.txt</a><br/>
          iTAK QR payload: <a href="{itak_txt}">qr.txt</a><br/>
          Browser QR payload: <a href="{browser_card_txt}">qr.txt</a><br/>
          Token URL: <code>{h(safe(token_url))}</code>
        </div>
      </div>
    </div>
  </div>

{script_html}
{brand_js_html}
</body></html>"""
