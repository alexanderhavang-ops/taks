from __future__ import annotations

from datetime import datetime, timezone

from takctl.onboarding.atak import atak_package_url


def _safe(v: object) -> str:
    return "" if v is None else str(v)


def _profile_block(*, username: str, groups: list[str], sel: dict) -> str:
    ctx = (sel or {}).get("ctx") or {}

    def g(k: str) -> str:
        v = ctx.get(k)
        return "" if v is None else str(v)

    unit = g("unit")
    company = g("company")
    platoon = g("platoon")
    role = g("role")
    policy_id = g("policy_id")
    n = g("n")

    groups_txt = ", ".join(groups or []) or "—"

    parts: list[str] = []
    parts.append(
        f'<div><b>Username</b>: <code id="taks_username">{_safe(username)}</code> '
        f'<button class="btn" onclick="copyId(\'taks_username\')">Copy</button></div>'
    )

    if unit or company or platoon or role:
        parts.append(
            f"<div><b>Unit</b>: <code>{_safe(unit) or '—'}</code> &nbsp; "
            f"<b>Company</b>: <code>{_safe(company) or '—'}</code> &nbsp; "
            f"<b>Platoon</b>: <code>{_safe(platoon) or '—'}</code></div>"
        )
        parts.append(
            f"<div><b>Role</b>: <code>{_safe(role) or '—'}</code> &nbsp; "
            f"<b>N</b>: <code>{_safe(n) or '—'}</code></div>"
        )

    if policy_id:
        parts.append(f"<div><b>Policy</b>: <code>{_safe(policy_id)}</code></div>")

    parts.append(f"<div><b>Groups</b>: <code>{_safe(groups_txt)}</code></div>")

    return '<div class="note">' + "<br/>".join(parts) + "</div>"


def _pw_block(*, username: str, ident, reveal_password: bool) -> str:
    if ident is None:
        return """
<div class="note">
  Password: <b>unknown</b> (no TAKS identity record)<br/>
  If created in Marti UI, TAKS does not know the password.
</div>
"""

    origin = getattr(ident, "origin", "marti")
    pw_known = bool(getattr(ident, "password_known", False))
    pw_val = getattr(ident, "password", None) if pw_known else None

    if not pw_known or origin != "taks":
        return f"""
<div class="note">
  Password: <b>unknown</b> (origin={_safe(origin)})<br/>
  This user appears created outside TAKS. Ask admin for out-of-band password or reset.
</div>
"""

    if not reveal_password:
        return f"""
<div class="note">
  Username: <code id="taks_username2">{_safe(username)}</code>
  <button class="btn" onclick="copyId('taks_username2')">Copy</button><br/>
  Password: <b>hidden</b> (admin chose out-of-band)
</div>
"""

    return f"""
<div class="note">
  Username: <code id="taks_username2">{_safe(username)}</code>
  <button class="btn" onclick="copyId('taks_username2')">Copy</button><br/>
  Password: <code id="taks_password">{_safe(pw_val)}</code>
  <button class="btn" onclick="copyId('taks_password')">Copy</button>
</div>
"""


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
) -> str:
    bump = int(datetime.now(timezone.utc).timestamp())
    # Token-scoped (public) endpoints
    atak_import_qr = f"{base}/api/onboarding/cards/{token}/packages/atak/qr.png?b={bump}"
    atak_import_txt = f"{base}/api/onboarding/cards/{token}/packages/atak/qr.txt?b={bump}"
    atak_pkg = f"{base}/api/onboarding/cards/{token}/packages/atak/package.zip"

    creds_html = _pw_block(username=username, ident=ident, reveal_password=reveal_password)
    profile_html = _profile_block(username=username, groups=groups, sel=sel)

    token_url = f"{base}/api/onboarding/cards/{token}"
    exp = expires_at_utc.replace(microsecond=0).isoformat()

    # Keep any braces in JS/CSS OUT of the f-string template itself.
    btn_css = """
    .btn { font-size: 12px; padding: 3px 8px; border: 1px solid #ddd; border-radius: 10px; background: #fff; cursor: pointer; }
    .btn:hover { background: #f6f6f6; }
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

    # IMPORTANT: keep JS in a non-f-string to avoid brace parsing.

    # IMPORTANT: keep JS in a non-f-string to avoid brace parsing.
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
</script>""".replace("__BUMP__", str(bump));
    # IMPORTANT: keep CSS in a non-f-string to avoid brace parsing.
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


    /* --- Splash-style brandchain in soldier card --- */
    .topbar { display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; margin-bottom: 10px; }
    .brand { display:flex; align-items:center; gap: 14px; flex-wrap:wrap; }

    .taksmark { display:inline-flex; align-items:center; justify-content:center; }
    .taksmark img {
      height: 26px;
      width: auto;
      display:block;
      filter: drop-shadow(0 6px 18px rgba(0,0,0,0.55));
    }

    .brandchain { display:flex; align-items:center; }
    .brandchain-row { display:flex; align-items:center; gap: 10px; flex-wrap:wrap; }

    .brandchain-row img {
      height: 24px;
      width: auto;
      max-width: 260px;
      object-fit: contain;
      display:block;
      filter: drop-shadow(0 2px 10px rgba(0,0,0,0.45));
    }

    /* Keep the chain from visually "squeezing" when space is tight */
    @media (max-width: 820px){
      .brand { gap: 10px; }
      .brandchain-row img { height: 22px; }
      .taksmark img { height: 24px; }
    }
    .topbar { display:flex; justify-content:space-between; gap:14px; align-items:center; flex-wrap:wrap; margin-bottom: 12px; }
    .brand { display:flex; align-items:center; gap:10px; flex-wrap:wrap; }


    .title { font-size: 20px; font-weight: 850; letter-spacing: 0.2px; }

    .hdr { display:flex; justify-content:space-between; gap:12px; flex-wrap:wrap; margin-bottom: 12px; }
    .meta { font-size: 12px; color: var(--muted); line-height: 1.35; }

    .section {
      margin-top: 14px;
      padding: 14px;
      border: 1px solid var(--bd);
      border-radius: 16px;
      background: rgba(0,0,0,0.25);
      backdrop-filter: blur(6px);
    }

    .grid { display:grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 12px; }

    .card {
      border: 1px solid var(--bd);
      border-radius: 16px;
      padding: 12px;
      background: var(--card);
      display:flex;
      flex-direction:column;
      gap:10px;
      box-shadow: 0 10px 30px rgba(0,0,0,0.25);
    }

    .card h3 { margin:0; font-size: 13px; color: rgba(255,255,255,0.88); letter-spacing: 0.2px; }

    .qr {
      display:flex;
      justify-content:center;
      padding: 12px;
      border: 1px dashed rgba(0,0,0,0.20);
      border-radius: 14px;
      background: #ffffff; /* keep QR on white */
    }
    .qr img { width: 280px; height: 280px; image-rendering: pixelated; }

    .links { font-size: 12px; line-height: 1.35; word-break: break-all; color: var(--muted); }
    .links a { color: var(--link); text-decoration:none; }
    .links a:hover { text-decoration:underline; }

    .note { font-size: 12px; color: var(--muted); line-height: 1.35; }

    code {
      background: rgba(255,255,255,0.08);
      border: 1px solid rgba(255,255,255,0.12);
      border-radius: 8px;
      padding: 2px 6px;
      color: rgba(255,255,255,0.92);
    }

    .btn {
      font-size: 12px;
      padding: 4px 10px;
      border: 1px solid rgba(255,255,255,0.14);
      border-radius: 999px;
      background: rgba(255,255,255,0.06);
      color: rgba(255,255,255,0.85);
      cursor: pointer;
    }
    .btn:hover { background: rgba(255,255,255,0.10); }
    </style>"""


    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Soldier Card for {username}</title>
    {style_html}
</head>
<body>
  <div class="topbar">
    <div class="brand">
      <div class="logos">
        <img alt="TAKS" style="height:26px;width:auto;display:block;object-fit:contain" src="{base}/assets/taks-logo.png?b={bump}" onerror="this.onerror=null;this.src='{base}/assets/taks-logo.svg?b={bump}'"/>
      </div>

      <div class="brandchain">
        <div class="brandchain-row" id="__brand_logos"></div>
      </div>
    </div>
  </div>

  {script_html}

  <div class="hdr">
    <div class="title">Soldier Card for <code>{username}</code></div>
    <div class="meta">
      Expires: <b>{exp}</b><br/>
      Token URL: <code id="taks_token_url">{token_url}</code>
      <button class="btn" onclick="copyId('taks_token_url')">Copy</button>
    </div>
  </div>

  <div class="section">
    <div class="note">
      1) Scan QR to import server defaults<br/>
      2) Enter credentials (if provided)<br/>
      3) Connect
    </div>

    <div class="grid">
      <div class="card">
        <h3>ATAK – Import package</h3>
        <div class="qr"><img alt="ATAK Import QR" src="{atak_import_qr}" /></div>
        <div class="links">
          QR payload: <a href="{atak_import_txt}">qr.txt</a><br/>
          Package: <a href="{atak_pkg}">{atak_pkg}</a>
        </div>
        <div class="note">After import: ATAK → Settings → TAK Server → (server) → Username/Password</div>
      </div>

      <div class="card">
        <h3>Profile</h3>
        {profile_html}
        <div class="note">If anything above looks wrong, stop and contact your admin before enrolling.</div>
      </div>

      <div class="card">
        <h3>Credentials</h3>
        {creds_html}
        <div class="note">
          If password is not shown, ask your admin (out-of-band) or have them reset it.
        </div>
      </div>
    </div>
  </div>
  {brand_js_html}
</body>
</html>
"""
