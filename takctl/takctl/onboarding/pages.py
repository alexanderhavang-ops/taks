from __future__ import annotations

from datetime import datetime, timezone

from takctl.onboarding.atak import atak_package_url, atak_package_creds_url
from takctl.onboarding.pages_soldier import render_soldier_card_page


def _now_utc_iso() -> str:
    from takctl.onboarding.atak import now_utc_iso
    return now_utc_iso()


def render_generate_page(*, username: str, groups: list[str], base: str, sel: dict) -> str:
    def chk(name: str, default: bool) -> str:
        v = (sel.get("paths", {}) or {}).get(name)
        on = default if v is None else bool(v)
        return "checked" if on else ""

    ctx = sel.get("ctx", {}) or {}
    from takctl.onboarding.policy_registry import default_policy_id
    policy_id = ctx.get("policy_id") or default_policy_id()
    unit = ctx.get("unit", "")
    n = ctx.get("n", "")
    role = ctx.get("role", "member")
    company = ctx.get("company", "")
    platoon = ctx.get("platoon", "")

    endpoints = sel.get("endpoints", {}) or {}
    enroll_host = endpoints.get("enroll_host", "")
    enroll_port = endpoints.get("enroll_port", "8446")
    enroll_ssl  = endpoints.get("enroll_ssl", "true")
    stream_host = endpoints.get("stream_host", "")
    stream_port = endpoints.get("stream_port", "8089")
    stream_ssl  = endpoints.get("stream_ssl", "true")

    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>TAKS Onboarding – Generate – {username}</title>
<style>
body {{ font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; margin: 22px; color:#111; }}
.hdr {{ display:flex; justify-content:space-between; gap:12px; flex-wrap:wrap; margin-bottom: 12px; }}
.title {{ font-size: 22px; font-weight: 800; }}
.meta {{ font-size: 13px; color:#444; }}
.box {{ border:1px solid #e6e6e6; border-radius: 14px; padding: 14px; background:#fff; margin-top: 12px; }}
.box h2 {{ margin:0 0 10px 0; font-size: 16px; }}
.grid {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; }}
label {{ display:flex; gap:10px; align-items:center; font-size: 13px; }}
input[type="text"], input[type="number"] {{ padding: 8px 10px; border:1px solid #ddd; border-radius: 10px; width: 100%; }}
.small {{ font-size: 12px; color:#555; line-height: 1.35; }}
.actions {{ display:flex; gap:10px; align-items:center; flex-wrap:wrap; margin-top: 12px; }}
button {{ padding: 10px 14px; border:1px solid #ccc; border-radius: 12px; background:#f7f7f7; cursor:pointer; font-weight:600; }}
a {{ color:#0a58ca; text-decoration:none; }}
a:hover {{ text-decoration:underline; }}
code {{ background:#f5f5f5; border:1px solid #eee; border-radius:6px; padding:2px 6px; }}
</style>
</head>
<body>
  <div class="hdr">
    <div class="title">Generate Onboarding</div>
    <div class="meta">User: <b>{username}</b> • Groups: <b>{", ".join(groups)}</b> • {base}</div>
  </div>

  <form method="post" action="{base}/api/onboarding/users/{username}/generate/submit">
    <div class="box">
      <h2>Clients to include</h2>
      <div class="grid">
        <div>
          <label><input type="checkbox" name="path_B" value="1" {chk("B", True)}/> <b>ATAK</b>: Import package (recommended)</label>
          <div class="small">One QR. Imports <code>config.pref</code>. User enters username/password manually in ATAK.</div>
        </div>
        <div>
          <label><input type="checkbox" name="path_itak" value="1" {chk("itak", True)}/> iTAK</label>
          <div class="small">Quick-connect text QR.</div>
        </div>
        <div>
          <label><input type="checkbox" name="path_wintak" value="1" {chk("wintak", True)}/> WinTAK</label>
          <div class="small">URL fallback QR.</div>
        </div>
      </div>
      <div class="small" style="margin-top:10px;">
        Note: enrollment deeplinks + credential injection are intentionally hidden until proven on real ATAK builds.
      </div>
    </div>

    <div class="box">
      <h2>Identity context (policy defaults)</h2>
      <div class="grid">
        <div><div class="small"><b>policy_id</b></div><input type="text" name="policy_id" value="{policy_id}"/></div>
        <div><div class="small"><b>unit</b></div><input type="text" name="unit" value="{unit}" placeholder="e.g. BSFB"/></div>
        <div><div class="small"><b>n</b></div><input type="text" name="n" value="{n}" placeholder="e.g. 1"/></div>
        <div><div class="small"><b>role</b></div><input type="text" name="role" value="{role}" placeholder="leader/member/staff"/></div>
        <div><div class="small"><b>company</b></div><input type="number" name="company" value="{company}" placeholder="e.g. 2"/></div>
        <div><div class="small"><b>platoon</b></div><input type="number" name="platoon" value="{platoon}" placeholder="e.g. 2"/></div>
      </div>
      <div class="small" style="margin-top:10px;">
        This drives callsign/team via policy (<code>takctl.onboarding.policy</code>).
      </div>
    </div>

    <div class="box">
      <h2>Endpoints (for experiments)</h2>
      <div class="grid">
        <div><div class="small"><b>Enroll endpoint</b> host</div><input type="text" name="enroll_host" value="{enroll_host}"/></div>
        <div><div class="small">port</div><input type="text" name="enroll_port" value="{enroll_port}"/></div>
        <div><div class="small">ssl</div><input type="text" name="enroll_ssl" value="{enroll_ssl}"/></div>

        <div><div class="small"><b>Stream endpoint</b> host</div><input type="text" name="stream_host" value="{stream_host}"/></div>
        <div><div class="small">port</div><input type="text" name="stream_port" value="{stream_port}"/></div>
        <div><div class="small">ssl</div><input type="text" name="stream_ssl" value="{stream_ssl}"/></div>
      </div>
      <div class="small" style="margin-top:10px;">
        Hints only. We validate real ports by testing + logs.
      </div>
    </div>

    <div class="box">
      <div class="actions">
        <button type="submit">Generate</button>
        <a href="{base}/api/onboarding/users/{username}/card">Go to card</a>
      </div>
    </div>
  </form>
</body></html>"""


def render_card_page(*, username: str, groups: list[str], base: str, sel: dict) -> str:
    bump = int(datetime.now(timezone.utc).timestamp())

    paths = sel.get("paths", {}) or {}
    want_B = bool(paths.get("B", True))
    want_itak = bool(paths.get("itak", True))
    want_wintak = bool(paths.get("wintak", True))

    atak_import_qr = f"{base}/api/onboarding/users/{username}/packages/atak/qr.png?b={bump}"
    atak_import_txt = f"{base}/api/onboarding/users/{username}/packages/atak/qr.txt?b={bump}"
    atak_pkg = atak_package_url(base, username)

    # Option C (experimental): package-creds QR + zip (password provided client-side; not stored)
    atak_pkg_creds_qr = f"{base}/api/onboarding/users/{username}/packages/atak/package-creds/qr.png"
    atak_pkg_creds_txt = f"{base}/api/onboarding/users/{username}/packages/atak/package-creds/qr.txt"
    atak_pkg_creds_zip = atak_package_creds_url(base, username)

    itak_qr = f"{base}/api/onboarding/users/{username}/packages/itak/qr.png?b={bump}"
    itak_txt = f"{base}/api/onboarding/users/{username}/packages/itak/qr.txt?b={bump}"

    wintak_qr = f"{base}/api/onboarding/users/{username}/packages/wintak/qr.png?b={bump}"
    wintak_txt = f"{base}/api/onboarding/users/{username}/packages/wintak/qr.txt?b={bump}"

    blocks: list[str] = []

    if want_B:
        blocks.append(f"""
  <div class="section">
    <h2>ATAK</h2>
    <div class="note">
      Recommended baseline:<br/>
      1) Scan the QR to import server + identity defaults.<br/>
      2) In ATAK, enter <b>Username/Password</b> manually.<br/>
      3) Connect.
      <br/><br/>
      After import: <code>ATAK → Settings → TAK Server → (server) → Username/Password</code>
    </div>

    <div class="grid">
      <div class="card">
        <h3>Import package (recommended)</h3>
        <div class="qr"><img alt="ATAK Import QR" src="{atak_import_qr}" /></div>
        <div class="links">
          QR payload: <a href="{atak_import_txt}">qr.txt</a><br/>
          Package: <a href="{atak_pkg}">{atak_pkg}</a>
        </div>
        <div class="note">
          Imports <code>config.pref</code> (server/identity defaults). Credentials are not embedded.
        </div>
      </div>

      <div class="card">
        <h3>Option C (Experimental) — Import package with embedded creds</h3>
        <div class="note">
          This tests whether ATAK will accept <code>username0</code>/<code>password0</code> from <code>config.pref</code>
          and stop prompting (or prefill).<br/>
          Password is <b>not stored</b> by TAKS; it is only used to generate the QR/package in your browser.
        </div>

        <div class="grid" style="grid-template-columns: 1fr; gap: 10px;">
          <div>
            <div class="small"><b>Password</b> (for <code>{username}</code>)</div>
            <input id="optc_pw" type="password" placeholder="Enter enrollment password" />
          </div>

          <div class="actions">
            <button type="button" id="optc_btn">Generate QR</button>
            <a id="optc_zip" href="#" target="_blank" rel="noopener noreferrer" style="display:none;">Download zip</a>
            <a id="optc_txt" href="#" target="_blank" rel="noopener noreferrer" style="display:none;">qr.txt</a>
          </div>

          <div class="qr" id="optc_qrwrap" style="display:none;">
            <img id="optc_qrimg" alt="ATAK Option C Import QR" src="" />
          </div>

          <div class="note" style="margin-top:-2px;">
            Endpoint: <code>{atak_pkg_creds_zip}</code>
          </div>
        </div>
      </div>
    </div>
  </div>
""")

    blocks.append(f"""
  <div class="section">
    <h2>Other clients</h2>
    <div class="note">
      Use when you don't know device type. (iTAK/WinTAK are best-effort.)
    </div>
    <div class="grid">
""")

    if want_itak:
        blocks.append(f"""
      <div class="card">
        <h3>iPhone/iPad — iTAK</h3>
        <div class="qr"><img alt="iTAK QR" src="{itak_qr}" /></div>
        <div class="links">
          QR payload: <a href="{itak_txt}">qr.txt</a>
        </div>
        <div class="note">iTAK QR is a Quick Connect text line.</div>
      </div>
""")

    if want_wintak:
        blocks.append(f"""
      <div class="card">
        <h3>Windows — WinTAK</h3>
        <div class="qr"><img alt="WinTAK QR" src="{wintak_qr}" /></div>
        <div class="links">
          QR payload: <a href="{wintak_txt}">qr.txt</a>
        </div>
        <div class="note">WinTAK QR is a URL fallback (manual download/import).</div>
      </div>
""")

    blocks.append("""
    </div>
  </div>
""")

    blocks.append(f"""
  <div class="section">
    <h2>Admin</h2>
    <div class="note">Config: <a href="{base}/api/onboarding/users/{username}/generate">Generate onboarding</a></div>
    <div class="note">
      • Screenshot-friendly<br/>
      • QRs are <code>no-store</code> and use cache-busting <code>?b=</code>
    </div>
  </div>
""")

    body_blocks = "\n".join(blocks)

    # JS for Option C: build qr.png + zip + txt URLs with password + cache-buster.
    optc_js = f"""
<script>
(function() {{
  function enc(s) {{ return encodeURIComponent(String(s || "")); }}
  var btn = document.getElementById("optc_btn");
  if (!btn) return;

  var pwEl = document.getElementById("optc_pw");
  var imgWrap = document.getElementById("optc_qrwrap");
  var img = document.getElementById("optc_qrimg");
  var zipA = document.getElementById("optc_zip");
  var txtA = document.getElementById("optc_txt");

  var qrBase = "{atak_pkg_creds_qr}";
  var zipBase = "{atak_pkg_creds_zip}";
  var txtBase = "{atak_pkg_creds_txt}";

  btn.addEventListener("click", function() {{
    var pw = (pwEl && pwEl.value ? pwEl.value : "").trim();
    if (!pw) {{
      alert("Password required for Option C");
      return;
    }}
    var b = Date.now();

    // IMPORTANT:
    // The password is passed as a query param so the backend can embed it into config.pref
    // inside the generated zip. ATAK cannot supply custom headers when downloading via QR.
    var qrUrl  = qrBase  + "?b=" + enc(b) + "&password=" + enc(pw);
    var zipUrl = zipBase + "&b=" + enc(b) + "&password=" + enc(pw);
    var txtUrl = txtBase + "?b=" + enc(b) + "&password=" + enc(pw);

    img.src = qrUrl;
    imgWrap.style.display = "flex";

    zipA.href = zipUrl;
    zipA.style.display = "inline";

    txtA.href = txtUrl;
    txtA.style.display = "inline";
  }});
}})();
</script>
"""

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>TAKS Onboarding – {username}</title>
  <style>
    body {{ font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; margin: 22px; color: #111; }}
    .hdr {{ display:flex; justify-content:space-between; gap:12px; flex-wrap:wrap; margin-bottom: 12px; }}
    .title {{ font-size: 22px; font-weight: 800; }}
    .meta {{ font-size: 13px; color:#444; }}
    .section {{ margin-top: 14px; padding: 14px; border: 1px solid #e6e6e6; border-radius: 14px; background: #fff; }}
    .section h2 {{ margin: 0 0 10px 0; font-size: 16px; }}
    .grid {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; }}
    .card {{ border: 1px solid #efefef; border-radius: 14px; padding: 12px; background: #fcfcfc; display:flex; flex-direction:column; gap:10px; }}
    .card h3 {{ margin:0; font-size: 14px; }}
    .qr {{ display:flex; justify-content:center; padding: 10px; border: 1px dashed #ddd; border-radius: 12px; background:#fff; }}
    .qr img {{ width: 230px; height: 230px; image-rendering: pixelated; }}
    .links {{ font-size: 12px; line-height: 1.35; word-break: break-all; }}
    .links a {{ color:#0a58ca; text-decoration:none; }}
    .links a:hover {{ text-decoration:underline; }}
    .note {{ font-size: 12px; color:#555; line-height: 1.35; }}
    .small {{ font-size: 12px; color:#555; line-height: 1.35; }}
    .actions {{ display:flex; gap:10px; align-items:center; flex-wrap:wrap; }}
    button {{ padding: 10px 14px; border:1px solid #ccc; border-radius: 12px; background:#f7f7f7; cursor:pointer; font-weight:600; }}
    input[type="password"] {{ padding: 8px 10px; border:1px solid #ddd; border-radius: 10px; width: 100%; }}
    code {{ background:#f5f5f5; border:1px solid #eee; border-radius:6px; padding:2px 6px; }}
    a {{ color:#0a58ca; text-decoration:none; }}
    a:hover {{ text-decoration:underline; }}
  </style>
</head>
<body>
  <div class="hdr">
    <div class="title">TAKS Onboarding Card</div>
    <div class="meta">
      User: <b>{username}</b> • Groups: <b>{", ".join(groups)}</b> • Generated: <b>{_now_utc_iso()}</b>
    </div>
  </div>

{body_blocks}

{optc_js}

</body>
</html>
"""
