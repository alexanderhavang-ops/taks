from __future__ import annotations

from html import escape as h
from pathlib import Path
from urllib.parse import urlparse

from takctl.config import load_config
from takctl.onboarding.soldier_card.i18n import lang_norm, t


def _read_murmur_server_password() -> str:
    p = Path("/opt/tak/tools/takctl/secrets.d/murmur.conf")
    try:
        txt = p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""
    for line in txt.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("serverpassword="):
            return line.split("=", 1)[1].strip()
    return ""


def _voice_host_for_card(base: str = "") -> str:
    try:
        if base:
            host = (urlparse(str(base)).hostname or "").strip()
            if host:
                return host
    except Exception:
        pass
    try:
        ext = str(load_config().get("onboarding_external_base", "") or "").strip()
        if ext:
            host = (urlparse(ext).hostname or "").strip()
            if host:
                return host
    except Exception:
        pass
    return ""


def _voice_setup_block(*, lang: str | None, base: str, token: str, bump: int | str) -> str:
    l = lang_norm(lang)
    voice_install_url = "https://play.google.com/store/apps/details?id=com.atakmap.android.gbr.vx.plugin"
    voice_host = _voice_host_for_card(base)
    voice_port = "64738"
    voice_password = _read_murmur_server_password()

    vx_zip = f"{base}/api/onboarding/cards/{token}/packages/vx/package.zip"
    vx_qr = f"{base}/api/onboarding/cards/{token}/packages/vx/qr.png?b={bump}"

    rows = []
    rows.append(f'Android Vx: <a href="{h(voice_install_url)}" target="_blank" rel="noopener">Install Vx</a><br/>')

    if voice_host:
        rows.append(
            'Server: <code id="murmur_host_post">' + h(voice_host) + '</code> '
            '<button class="btn interactive-only" onclick="copyId(\'murmur_host_post\')">' + h(t(l, "soldier.copy")) + '</button><br/>'
        )
    else:
        rows.append('Server: <span class="muted">not configured</span><br/>')

    rows.append(
        'Port: <code id="murmur_port_post">' + h(voice_port) + '</code> '
        '<button class="btn interactive-only" onclick="copyId(\'murmur_port_post\')">' + h(t(l, "soldier.copy")) + '</button><br/>'
    )

    if voice_password:
        rows.append(
            'Voice password: <code id="murmur_password_post">' + h(voice_password) + '</code> '
            '<button class="btn interactive-only" onclick="copyId(\'murmur_password_post\')">' + h(t(l, "soldier.copy")) + '</button><br/>'
        )
    else:
        rows.append('Voice password: <span class="muted">not configured</span><br/>')

    rows.append('Import Vx package into ATAK after the plugin is installed.<br/>')
    rows.append('iPhone/iTAK: use a separate Mumble client with the same server, port and password.')

    return f"""
    <div class="stepcard">
      <h4>Röst</h4>
      <div class="muted">Installera Vx, importera Vx-paketet i ATAK och anslut sedan mot Murmur-servern.</div>
      <div style="margin-top:10px;"><img class="qrimg" src="{h(vx_qr)}" alt="Vx package QR"/></div>
      <div class="dlrow">
        <a class="btn" href="{h(vx_zip)}">Hämta Vx-paket</a>
        <a class="btn" href="{h(vx_qr)}">Öppna QR</a>
      </div>
      <div style="margin-top:12px; line-height:1.7;">
        {''.join(rows)}
      </div>
    </div>
    """


def _placeholder_card(title: str, text: str) -> str:
    return f"""
    <div class="stepcard">
      <h4>{h(title)}</h4>
      <div class="muted">{h(text)}</div>
    </div>
    """


def post_onboarding_block(*, lang: str | None, base: str, token: str, bump: int | str) -> str:
    return f"""
    <div class="guidegrid">
      {_voice_setup_block(lang=lang, base=base, token=token, bump=bump)}
      {_placeholder_card("Kartor", "Reserverat för kartpaket och offlinekartor.")}
      {_placeholder_card("Tillägg", "Reserverat för fler pluginer och framtida nedladdningar.")}
    </div>
    """
