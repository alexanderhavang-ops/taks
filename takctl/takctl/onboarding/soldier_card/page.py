from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from html import escape as h
from urllib.parse import urlparse

from takctl.onboarding.soldier_card.blocks import lifecycle_block, password_block, profile_block
from takctl.onboarding.soldier_card.post_onboarding import post_onboarding_block
from takctl.onboarding.soldier_card.status import mobile_flow_btn_extra_class
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


def _show_soft_cert_paths(cfg) -> bool:
    del cfg
    return True


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


def _print_pack_style_html() -> str:
    return """<style>
@page {
  size: A4 portrait;
  margin: 10mm;
}
html, body {
  margin: 0;
  padding: 0;
  background: #ffffff;
  color: #111111;
}
body.print-pack {
  background: #ffffff;
  color: #111111;
  font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;
}
.print-pack-wrap {
  width: 100%;
}
.print-page {
  page-break-after: always;
  break-after: page;
  padding: 0;
  margin: 0;
}
.print-page:last-child {
  page-break-after: auto;
  break-after: auto;
}
.print-password-page {
  page-break-after: always;
  break-after: page;
  padding: 0;
  margin: 0;
}
.print-password-page:last-child {
  page-break-after: auto;
  break-after: auto;
}
.print-card-shell {
  padding: 0;
}
.print-password-shell {
  border: 1px solid #cfcfcf;
  border-radius: 10px;
  overflow: hidden;
  background: #fff;
}
.print-password-topbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  background: linear-gradient(180deg, #1f2328 0%, #111418 100%);
  color: #fff;
  border-bottom: 3px solid #b08d2f;
}
.print-password-title {
  font-size: 24px;
  font-weight: 900;
  line-height: 1.05;
}
.print-password-subtitle {
  font-size: 15px;
  color: rgba(255,255,255,0.82);
  margin-top: 3px;
}
.print-password-box {
  border: 1px solid #d8d8d8;
  border-radius: 10px;
  padding: 14px;
  margin-top: 14px;
  background: #fff;
}
.print-row {
  display: grid;
  grid-template-columns: 160px minmax(0,1fr);
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}
.print-label {
  font-size: 11px;
  color: #6d7278;
  font-weight: 800;
  text-transform: uppercase;
  white-space: nowrap;
  letter-spacing: 0.04em;
}
.print-value {
  font-size: 15px;
  line-height: 1.25;
}
.print-mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}
.print-big {
  font-size: 22px;
  line-height: 1.2;
  font-weight: 800;
  word-break: break-all;
}
@media screen {
  body.print-pack {
    background: #e9e9e9;
  }
  .print-page,
  .print-password-page {
    width: 210mm;
    min-height: 297mm;
    margin: 0 auto 8mm auto;
    background: #fff;
    padding: 10mm;
    box-sizing: border-box;
  }
}
@media print {
  .interactive-only {
    display: none !important;
  }
}
</style>"""


def render_soldier_card_print_pack(*, title: str, sections: list[str]) -> str:
    body = "\n".join(sections) if sections else """
<div class="print-page">
  <div class="print-card-shell">
    <div style="font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; padding: 24px;">
      <h1 style="margin:0 0 12px 0; font-size:28px;">TAKS</h1>
      <div>No users selected.</div>
    </div>
  </div>
</div>
"""
    return f"""<!doctype html>
<html lang="sv">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>{h(title)}</title>
  {_print_pack_style_html()}
</head>
<body class="print-pack">
  <div class="print-pack-wrap">
    {body}
  </div>
</body>
</html>
"""


def _render_password_only_section(
    *,
    lang: str,
    username: str,
    groups: list[str],
    sel: dict,
    ident,
) -> str:
    profile_html = profile_block(lang=lang, username=username, groups=groups, sel=sel, ident=ident)
    creds_html = password_block(
        lang=lang,
        username=username,
        ident=ident,
        reveal_password=True,
        truststore_password=None,
        client_password=None,
    )

    return f"""
<div class="print-password-page">
  <div class="print-password-shell">
    <div class="print-password-topbar">
      <div>
        <div style="font-size:11px;text-transform:uppercase;letter-spacing:0.08em;color:rgba(255,255,255,0.72);font-weight:700;">TAKS</div>
        <div class="print-password-title">{h(t(lang, "soldier.title_for", username=username))}</div>
        <div class="print-password-subtitle">{h(t(lang, "soldier.credentials"))}</div>
      </div>
    </div>
    <div style="padding:14px;">
      <div class="print-password-box">
        <div style="font-size:11px;text-transform:uppercase;letter-spacing:0.09em;color:#6d7278;font-weight:800;margin-bottom:12px;">{h(t(lang, "soldier.profile"))}</div>
        {profile_html}
      </div>
      <div class="print-password-box">
        <div style="font-size:11px;text-transform:uppercase;letter-spacing:0.09em;color:#6d7278;font-weight:800;margin-bottom:12px;">{h(t(lang, "soldier.credentials"))}</div>
        {creds_html}
      </div>
    </div>
  </div>
</div>
"""


def _render_full_card_section(
    *,
    lang: str,
    username: str,
    groups: list[str],
    base: str,
    sel: dict,
    ident,
    token: str,
    expires_at_utc: datetime,
    reveal_password: bool,
    lifecycle: dict | None,
    interactive: bool,
) -> str:
    bump = int(datetime.now(timezone.utc).timestamp())
    l = lang_norm(lang)

    cfg = load_config()
    show_soft_cert_paths = _show_soft_cert_paths(cfg)

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
    itak_soft_cert_qr_png = f"{base}/api/onboarding/cards/{token}/packages/itak/soft-cert/qr.png?b={bump}"
    itak_soft_cert_qr_txt = f"{base}/api/onboarding/cards/{token}/packages/itak/soft-cert/qr.txt?b={bump}"
    itak_soft_cert_zip = f"{base}/api/onboarding/cards/{token}/packages/itak/soft-cert/package.zip"

    browser_card_qr = f"{base}/api/onboarding/cards/{token}/card-url/qr.png?b={bump}"
    browser_card_txt = f"{base}/api/onboarding/cards/{token}/card-url/qr.txt?b={bump}"

    profile_html = profile_block(lang=l, username=username, groups=groups, sel=sel, ident=ident)
    lifecycle_html = lifecycle_block(l, lifecycle)
    post_onboarding_html = post_onboarding_block(lang=l, base=base, token=token, bump=bump)
    mobile_btn_extra = mobile_flow_btn_extra_class(lifecycle)

    truststore_password = None
    client_password = None
    if (not soft_cert_include_truststore_password) and reveal_truststore_password_on_soldier_card:
        truststore_password = _read_runtime_ca_password() or None
    if (not soft_cert_include_client_password) and reveal_client_password_on_soldier_card:
        client_password = _read_user_client_password(username) or _read_runtime_user_cert_password() or None

    creds_html = password_block(
        lang=l,
        username=username,
        ident=ident,
        reveal_password=reveal_password,
        truststore_password=truststore_password,
        client_password=client_password,
    )

    if show_soft_cert_paths:
        mode_label = "soft-cert / cert-creation"
        mode_summary_html = (
            f'<div class="meta" style="margin-top:8px;">'
            f'{h(t(l, "soldier.mode_label"))}: <code>{h(mode_label)}</code> · '
            f'{h(t(l, "soldier.mode.client_pw_embedded"))}: <code>{"yes" if soft_cert_include_client_password else "no"}</code> · '
            f'{h(t(l, "soldier.mode.trust_pw_embedded"))}: <code>{"yes" if soft_cert_include_truststore_password else "no"}</code>'
            f"</div>"
        )
    else:
        mode_label = "auto-enroll / quick connect"
        mode_summary_html = (
            f'<div class="meta" style="margin-top:8px;">'
            f'{h(t(l, "soldier.mode_label"))}: <code>{h(mode_label)}</code> · '
            f'{h(t(l, "soldier.mode.userpass_short"))}'
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
    .hero-nameplate { margin-top:18px; height:86px; min-width:260px; max-width:460px; border-radius:6px; padding:12px 14px; background:#244a82; box-shadow:0 8px 18px rgba(0,0,0,0.38); border:1px solid rgba(0,0,0,0.12); display:flex; flex-direction:column; justify-content:center; gap:6px; overflow:hidden; }
    .hero-nameplate-callsign { font-family:ui-sans-serif,system-ui,-apple-system,'Segoe UI',Roboto,Arial,sans-serif; font-weight:900; font-size:20px; line-height:1.0; letter-spacing:0.02em; text-transform:uppercase; color:#fff; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
    .hero-nameplate-row2 { font-family:ui-sans-serif,system-ui,-apple-system,'Segoe UI',Roboto,Arial,sans-serif; font-weight:800; font-size:12px; line-height:1.0; letter-spacing:0.06em; text-transform:uppercase; color:rgba(255,255,255,0.92); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
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
      var ids = ["start", "guide", "info", "post", "advanced"];
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
    .choicebtn-ok { background: rgba(68,108,62,0.48); border-color: rgba(154,205,136,0.34); color:#ecffe7; }
    .choicebtn-ok:hover { background: rgba(78,122,72,0.56); }
    .choicebtn-ok.choicebtn-active { outline:2px solid rgba(154,205,136,0.45); }
a { color: var(--link); }
pre { white-space: pre-wrap; word-break: break-word; }
.print-page > div[id^="tab_"],
.print-page > div[id^="flow_"] { display:block !important; }
.print-page .tabs.interactive-only,
.print-page .choicebtn.interactive-only,
.print-page .interactive-only,
.print-page .dlrow,
.print-page .btn,
.print-page a.btn { display:none !important; }
.print-page #tab_info { display:none !important; }

.print-page .card,
.print-page .stepcard,
.print-page .guidegrid > .stepcard,
.print-page .infogrid > .stepcard {
  background: #ffffff !important;
  color: #111111 !important;
  border-color: #d8d8d8 !important;
  box-shadow: none !important;
}

.print-page .hero {
  background: #f3f5f8 !important;
  color: #111111 !important;
  border: 1px solid #d8d8d8 !important;
  box-shadow: none !important;
}

.print-page .hero * {
  text-shadow: none !important;
}

.print-page .hero-title,
.print-page .hero-title * {
  color: #111111 !important;
}

.print-page .hero-sub,
.print-page .hero-sub * {
  color: #555555 !important;
}

.print-page .muted,
.print-page .muted * {
  color: #555555 !important;
}

.print-page .slogan,
.print-page .slogan * {
  color: #555555 !important;
}

.print-page .hero .meta,
.print-page .hero .meta * {
  color: #555555 !important;
}

.print-page .eyebrow,
.print-page .eyebrow * {
  color: #355d9a !important;
}

.print-page .hero code,
.print-page .hero code * {
  background: #eef2f7 !important;
  color: #111111 !important;
  border: 1px solid #d8d8d8 !important;
}

.print-page code,
.print-page code.inline {
  background: #f3f5f8 !important;
  color: #111111 !important;
  border: 1px solid #d8d8d8 !important;
  padding: 1px 4px !important;
  border-radius: 4px !important;
}

.print-page strong,
.print-page b {
  color: #111111 !important;
}

.print-page ::selection {
  background: transparent !important;
  color: inherit !important;
}

.print-page a,
.print-page a:visited {
  color: #111111 !important;
}

.print-page .danger-note {
  background: #fff8e8 !important;
  color: #6a4b00 !important;
  border: 1px solid #e6cf95 !important;
}

.print-page .qrimg {
  background: #ffffff !important;
  border: 1px solid #d8d8d8 !important;
}

.print-nameplate {
  margin-bottom: 14px;
  padding: 12px 14px;
  border: 1px solid #d8d8d8;
  border-radius: 12px;
  background: linear-gradient(180deg, #1f4b87 0%, #183b6b 100%);
  color: #ffffff !important;
  box-shadow: none !important;
}
.print-nameplate .print-nameplate-callsign {
  font-size: 22px;
  font-weight: 900;
  line-height: 1.05;
  margin: 0 0 4px 0;
  color: #ffffff !important;
}
.print-nameplate .print-nameplate-meta {
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: rgba(255,255,255,0.88) !important;
  font-weight: 700;
}

.print-page .topbar,
.print-page .topbar * {
  color: #555555 !important;
}

.print-page .topbar strong,
.print-page .topbar code {
  color: #111111 !important;
}
</style>"""

    android_cards = []

    if atak_qr_quick_connect_enabled:
        android_cards.append(f"""
        <div class="stepcard">
          <h4>ATAK quick-connect QR</h4>
          <div class="muted">{h(t(l, "soldier.path.atak_qr"))}</div>
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
          <div class="muted">{h(t(l, "soldier.path.atak_auto_zip"))}</div>
          <div style="margin-top:10px;"><img class="qrimg" src="{h(atak_qr_auto_enroll_png)}" alt="ATAK auto-enroll zip QR"/></div>
          <div class="dlrow">
            <a class="btn" href="{h(atak_auto_enroll_zip)}">{h(t(l, "soldier.download_zip"))}</a>
            <a class="btn" href="{h(atak_qr_auto_enroll_png)}">{h(t(l, "soldier.open_qr"))}</a>
            <a class="btn" href="{h(atak_qr_auto_enroll_txt)}">{h(t(l, "soldier.open_text"))}</a>
          </div>
        </div>
        """)

    if atak_qr_soft_cert_zip_enabled:
        android_cards.append(f"""
        <div class="stepcard">
          <h4>ATAK soft-cert zip</h4>
          <div class="muted">{h(t(l, "soldier.path.atak_soft_zip"))}</div>
          <div style="margin-top:10px;"><img class="qrimg" src="{h(atak_qr_soft_cert_png)}" alt="ATAK soft-cert zip QR"/></div>
          <div class="dlrow">
            <a class="btn" href="{h(atak_soft_cert_zip)}">{h(t(l, "soldier.download_zip"))}</a>
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
          <div class="muted">{h(t(l, "soldier.path.itak_qr"))}</div>
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
          <div class="muted">{h(t(l, "soldier.path.itak_soft_zip"))}</div>
          <div style="margin-top:10px;"><img class="qrimg" src="{h(itak_soft_cert_qr_png)}" alt="iTAK soft-cert zip QR"/></div>
          <div class="dlrow">
            <a class="btn" href="{h(itak_soft_cert_qr_png)}">{h(t(l, "soldier.open_qr"))}</a>
            <a class="btn" href="{h(itak_soft_cert_qr_txt)}">{h(t(l, "soldier.open_text"))}</a>
            <a class="btn" href="{h(itak_soft_cert_zip)}">{h(t(l, "soldier.download_zip"))}</a>
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

    root_cls = "card"
    if not interactive:
        root_cls += " print-expanded"

    tabs_top = ""
    if interactive:
        tabs_top = f"""
    <div class="tabs interactive-only">
      <button id="tabbtn_start" class="choicebtn" onclick="showMainTab('start')">{h(t(l, "soldier.start"))}</button>
      <button id="tabbtn_guide" class="choicebtn" onclick="showMainTab('guide')">{h(t(l, "soldier.guide"))}</button>
    <button class="choicebtn interactive-only" id="tabbtn_info" onclick="showMainTab('info')">Din info</button>
      \1
    <button class="choicebtn interactive-only" id="tabbtn_post" onclick="showMainTab('post')">Steg 2</button>
      <button id="tabbtn_advanced" class="choicebtn" onclick="showMainTab('advanced')">{h(t(l, "soldier.advanced_tab"))}</button>
    </div>
"""

    flow_tabs = ""
    if interactive:
        flow_tabs = f"""
      <div class="tabs interactive-only" style="margin-top:6px;">
        <button id="btn_android" class="choicebtn{mobile_btn_extra}" onclick="showFlow('android')">{h(t(l, "soldier.android"))}</button>
        <button id="btn_iphone" class="choicebtn{mobile_btn_extra}" onclick="showFlow('iphone')">{h(t(l, "soldier.iphone"))}</button>
        <button id="btn_browser" class="choicebtn" onclick="showFlow('browser')">{h(t(l, "soldier.browser"))}</button>
      </div>
"""

    info_section = ""
    if interactive:
        info_section = f"""
    <div id="tab_info" style="display:none; margin-top:12px;">
      {info_html}
    </div>
"""

    print_nameplate_html = ""
    if not interactive:
        callsign = ""
        try:
            callsign = str(((getattr(ident, "identity", None) or {}).get("callsign")) or username)
        except Exception:
            callsign = username
        meta_bits = []
        if groups:
            meta_bits.append(" / ".join([h(str(x)) for x in groups if str(x).strip()]))
        if token:
            meta_bits.append(h(t(l, "soldier.mode_label")) + ": " + h(mode_label))
        print_nameplate_html = f"""
  <div class="print-nameplate">
    <div class="print-nameplate-callsign">{h(callsign or username)}</div>
    <div class="print-nameplate-meta">{' • '.join(meta_bits) if meta_bits else h(username)}</div>
  </div>
"""

    hero_badge_callsign = ""
    try:
        hero_badge_callsign = str(((getattr(ident, "identity", None) or {}).get("callsign")) or username)
    except Exception:
        hero_badge_callsign = username

    hero_badge_ident = {}
    try:
        hero_badge_ident = dict(getattr(ident, "identity", None) or {})
    except Exception:
        hero_badge_ident = {}

    hero_badge_bits = []
    hero_battalion_fal = str(hero_badge_ident.get("battalion_fal") or "").strip()
    hero_battalion = str(hero_badge_ident.get("battalion") or "").strip()
    hero_company = str(hero_badge_ident.get("company") or "").strip()
    hero_platoon = str(hero_badge_ident.get("platoon") or "").strip()
    hero_group = str(hero_badge_ident.get("group") or "").strip()
    hero_n = str(hero_badge_ident.get("n") or "").strip()

    if hero_battalion_fal:
        hero_badge_bits.append(hero_battalion_fal)
    elif hero_battalion:
        hero_badge_bits.append(f"{hero_battalion} HVBAT")
    if hero_company:
        hero_badge_bits.append(t(l, "unit.company", n=hero_company))
    if hero_platoon:
        hero_badge_bits.append(t(l, "unit.platoon", n=hero_platoon))
    if hero_group:
        hero_badge_bits.append(t(l, "unit.group", n=hero_group))
    if hero_n:
        hero_badge_bits.append(f"EN {hero_n}")

    hero_badge_row2 = " · ".join([str(x) for x in hero_badge_bits if str(x).strip()])
    if not hero_badge_row2 and groups:
        hero_badge_row2 = " / ".join([str(x) for x in groups if str(x).strip()])
    if not hero_badge_row2:
        hero_badge_row2 = username

    hero_nameplate_html = f"""
    <div class="hero-nameplate">
      <div class="hero-nameplate-callsign">{h(hero_badge_callsign or username)}</div>
      <div class="hero-nameplate-row2">{h(hero_badge_row2 or username)}</div>
    </div>
"""

    hero_logo_html = f"""
    <div style="margin:12px 0 10px 0;">
      <img
        src="/assets/branding/node/unit.png?b={bump}"
        alt="Unit"
        style="display:block;width:auto;height:56px;max-width:220px;"
        onerror="this.onerror=null;this.src='/assets/branding/node/unit.png?b={bump}';"
      />
    </div>
    """

    body = f"""
  <div class="topbar">
    <div class="brand">
      <div class="taksmark"><img src="/assets/taks-logo.png?b={bump}" alt="TAKS"/></div>
      <div class="brandchain-row" id="__brand_logos"></div>
    </div>
    <div class="meta">
      <div>{h(t(l, "soldier.user_label"))}: <strong>{h(username)}</strong></div>
      <div>{h(t(l, "soldier.token_expires_label"))}: <code>{h(exp)}</code></div>
    </div>
  </div>

  <div class="hero">
    <div class="eyebrow">TAKS ONBOARDING</div>
    {hero_logo_html}
    <div class="hero-title">{h(t(l, "soldier.welcome"))}</div>
    <div class="hero-sub">{h(t(l, "soldier.subtitle"))}</div>
    {hero_nameplate_html}
    {f'<div class="slogan">{h(brand_slogan)}</div>' if brand_slogan else ''}
    {mode_summary_html}
  </div>

  <div class="{root_cls}">
    {print_nameplate_html}
    {tabs_top}

    <div id="tab_start">
      {flow_tabs}
      <div id="flow_android" style="margin-top:12px;">{android_html}</div>
      <div id="flow_iphone" style="margin-top:12px; {'display:none;' if interactive else ''}">{iphone_html}</div>
      <div id="flow_browser" style="margin-top:12px; {'display:none;' if interactive else ''}">{browser_html}</div>
    </div>

    <div id="tab_guide" style="{'display:none;' if interactive else ''} margin-top:12px;">
      {guide_html}
    </div>

    {info_section}

    {f'''
    <div id="tab_post" style="display:none; margin-top:12px;">
      <div class="stepcard">
        <h4>Post Onboarding</h4>
        <div class="muted">Setup that happens after TAK import and account activation.</div>
        <div style="margin-top:12px;">{post_onboarding_html}</div>
      </div>
    </div>


    <div id="tab_advanced" style="display:none; margin-top:12px;">
      <div class="stepcard">
        <h4>{h(t(l, "soldier.card_url"))}</h4>
        <div class="muted" id="card_url_txt">{h(token_url)}</div>
        <div class="dlrow">
          <button class="btn interactive-only" onclick="copyId('card_url_txt')">{h(t(l, "soldier.copy"))}</button>
          <a class="btn" href="{h(token_url)}">{h(t(l, "soldier.open_card"))}</a>
        </div>
      </div>
    </div>
    ''' if interactive else ''}
  </div>
"""

    if interactive:
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
  {body}
  {script_html}
  {brand_js_html}
</body>
</html>
"""

    return f"""
<div class="print-page">
  <div class="print-card-shell">
    {style_html}
    <style>{btn_css}</style>
    {body}
  </div>
</div>
"""


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
    render_mode: str = "interactive",
) -> str:
    l = lang_norm(lang)
    mode = str(render_mode or "interactive").strip().lower()

    if mode == "print_password":
        return _render_password_only_section(
            lang=l,
            username=username,
            groups=groups,
            sel=sel,
            ident=ident,
        )

    interactive = (mode == "interactive")
    return _render_full_card_section(
        lang=l,
        username=username,
        groups=groups,
        base=base,
        sel=sel,
        ident=ident,
        token=token,
        expires_at_utc=expires_at_utc,
        reveal_password=reveal_password,
        lifecycle=lifecycle,
        interactive=interactive,
    )


__all__ = ["render_soldier_card_page", "render_soldier_card_print_pack"]
