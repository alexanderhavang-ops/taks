from __future__ import annotations

from datetime import datetime, timezone

from takctl.onboarding.atak import atak_package_url


def _safe(v: object) -> str:
    return "" if v is None else str(v)


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
  Username: <code>{_safe(username)}</code><br/>
  Password: <b>hidden</b> (admin chose out-of-band)
</div>
"""

    return f"""
<div class="note">
  Username: <code>{_safe(username)}</code><br/>
  Password: <code>{_safe(pw_val)}</code>
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

    atak_import_qr = f"{base}/api/onboarding/users/{username}/packages/atak/qr.png?b={bump}"
    atak_import_txt = f"{base}/api/onboarding/users/{username}/packages/atak/qr.txt?b={bump}"
    atak_pkg = atak_package_url(base, username)

    creds_html = _pw_block(username=username, ident=ident, reveal_password=reveal_password)

    exp = expires_at_utc.replace(microsecond=0).isoformat()

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>TAKS Onboarding</title>
  <style>
    body {{ font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; margin: 22px; color: #111; }}
    .hdr {{ display:flex; justify-content:space-between; gap:12px; flex-wrap:wrap; margin-bottom: 12px; }}
    .title {{ font-size: 22px; font-weight: 800; }}
    .meta {{ font-size: 13px; color:#444; }}
    .section {{ margin-top: 14px; padding: 14px; border: 1px solid #e6e6e6; border-radius: 14px; background: #fff; }}
    .grid {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; }}
    .card {{ border: 1px solid #efefef; border-radius: 14px; padding: 12px; background: #fcfcfc; display:flex; flex-direction:column; gap:10px; }}
    .card h3 {{ margin:0; font-size: 14px; }}
    .qr {{ display:flex; justify-content:center; padding: 10px; border: 1px dashed #ddd; border-radius: 12px; background:#fff; }}
    .qr img {{ width: 260px; height: 260px; image-rendering: pixelated; }}
    .links {{ font-size: 12px; line-height: 1.35; word-break: break-all; }}
    .links a {{ color:#0a58ca; text-decoration:none; }}
    .links a:hover {{ text-decoration:underline; }}
    .note {{ font-size: 12px; color:#555; line-height: 1.35; }}
    code {{ background:#f5f5f5; border:1px solid #eee; border-radius:6px; padding:2px 6px; }}
  </style>
</head>
<body>
  <div class="hdr">
    <div class="title">TAKS Onboarding</div>
    <div class="meta">Expires: <b>{exp}</b></div>
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
        <h3>Credentials</h3>
        {creds_html}
        <div class="note">
          If password is not shown, ask your admin (out-of-band) or have them reset it.
        </div>
      </div>
    </div>
  </div>

</body>
</html>
"""
