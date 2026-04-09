from __future__ import annotations

from html import escape as h
from pathlib import Path
from urllib.parse import urlparse

from takctl.config import load_config
from takctl.onboarding.soldier_card.i18n import lang_norm, t


MURMUR_SECRET_FILES = (
    Path("/opt/tak/tools/takctl/secrets.d/murmur.conf"),
    Path("/opt/tak/bootstrap/secrets.d/murmur.conf"),
)

_TEXT = {
    "en": {
        "voice.title": "Voice",
        "voice.subtitle": "Recommended flow for TAK Voice with Martine onboarding.",
        "voice.step1.pre": 'Download and install the Android app ',
        "voice.step1.post": '. Then open ATAK again and tap Yes in the dialog that asks to install the Vx plugin.',
        "voice.step2": "Ask Martine to onboard you for voice in the ATAK chat: ",
        "voice.step3": "Martine installs the voice package in ATAK in the background. Then go to Settings -> TAK Voice, open the voice package for your unit, and choose channels for VS1 and VS2. You can run two voice channels at the same time.",
        "voice.step4": "When you assign the channels, Vx will ask for the Mumble server password. Martine gives you that password in chat, and it is also shown on this soldier card.",
        "voice.server": "Server",
        "voice.port": "Port",
        "voice.password": "Mumble server password",
        "voice.not_configured": "not configured",
        "maps.title": "Maps",
        "maps.body": "Reserved for map packages and offline maps.",
        "addons.title": "Add-ons",
        "addons.body": "Reserved for more plugins and future downloads.",
    },
    "sv": {
        "voice.title": "Röst",
        "voice.subtitle": "Rekommenderat flöde för TAK Voice med Martine-onboarding.",
        "voice.step1.pre": 'Ladda ner och installera Android-appen ',
        "voice.step1.post": '. Öppna sedan ATAK igen och tryck Ja i dialogen som frågar om du vill installera Vx-pluginet.',
        "voice.step2": "Be Martine onboarda dig för voice i ATAK-chatten: ",
        "voice.step3": "Martine installerar voice-paketet i ATAK i bakgrunden. Gå sedan till Settings -> TAK Voice, öppna voice-paketet för din enhet och välj kanaler för VS1 och VS2. Du kan ha två voice-kanaler igång samtidigt.",
        "voice.step4": "När du väljer kanaler frågar Vx efter Mumble-serverns lösenord. Martine ger dig det lösenordet i chatten, och det visas också här på soldatkortet.",
        "voice.server": "Server",
        "voice.port": "Port",
        "voice.password": "Mumble-serverlösenord",
        "voice.not_configured": "inte konfigurerat",
        "maps.title": "Kartor",
        "maps.body": "Reserverat för kartpaket och offlinekartor.",
        "addons.title": "Tillägg",
        "addons.body": "Reserverat för fler pluginer och framtida nedladdningar.",
    },
}


def _cfg_get(cfg, key: str, default: str = "") -> str:
    if cfg is None:
        return default
    try:
        if hasattr(cfg, "get"):
            val = cfg.get(key, default)
            if val is not None:
                return val
    except Exception:
        pass
    try:
        val = getattr(cfg, key)
        if val is not None:
            return val
    except Exception:
        pass
    return default


def _s(lang: str | None, key: str) -> str:
    l = lang_norm(lang)
    table = _TEXT.get(l, _TEXT["en"])
    return str(table.get(key, _TEXT["en"].get(key, key)))


def _read_simple_kv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        txt = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return out

    for raw in txt.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip().lower()
        v = v.strip()
        if k:
            out[k] = v
    return out


def _read_murmur_server_password() -> str:
    for p in MURMUR_SECRET_FILES:
        rows = _read_simple_kv(p)
        for key in ("serverpassword", "mumble_server_password", "server_password"):
            val = str(rows.get(key) or "").strip()
            if val:
                return val
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
        cfg = load_config()
    except Exception:
        cfg = None

    for key in (
        "onboarding_external_base",
        "fqdn",
        "node_fqdn",
        "tak_public_host",
        "public_host",
    ):
        raw = str(_cfg_get(cfg, key, "") or "").strip()
        if not raw:
            continue
        try:
            if "://" in raw:
                host = (urlparse(raw).hostname or "").strip()
            else:
                host = raw.strip()
        except Exception:
            host = raw.strip()
        if host:
            return host

    return ""


def _kv_row(*, label: str, element_id: str, value: str, lang: str | None) -> str:
    if value:
        return (
            f'{h(label)}: <code id="{h(element_id)}">{h(value)}</code> '
            f'<button class="btn interactive-only" onclick="copyId(\'{h(element_id)}\')">{h(t(lang_norm(lang), "soldier.copy"))}</button><br/>'
        )
    return f'{h(label)}: <span class="muted">{h(_s(lang, "voice.not_configured"))}</span><br/>'


def _voice_setup_block(*, lang: str | None, base: str, token: str, bump: int | str) -> str:
    del token, bump  # voice flow is Martine-led now; keep signature stable for callers

    l = lang_norm(lang)
    voice_install_url = "https://play.google.com/store/apps/details?id=com.atakmap.android.gbr.vx.plugin"
    voice_host = _voice_host_for_card(base)
    voice_port = "64738"
    voice_password = _read_murmur_server_password()

    steps = [
        (
            _s(l, "voice.step1.pre")
            + f'<a href="{h(voice_install_url)}" target="_blank" rel="noopener">ATAK Plugin: Vx</a>'
            + _s(l, "voice.step1.post")
        ),
        _s(l, "voice.step2") + "<code>Onboard me for voice</code>" if l == "en" else _s(l, "voice.step2") + "<code>Onboarda mig för voice</code>",
        _s(l, "voice.step3"),
        _s(l, "voice.step4"),
    ]

    rows = [
        _kv_row(label=_s(l, "voice.server"), element_id="murmur_host_post", value=voice_host, lang=l),
        _kv_row(label=_s(l, "voice.port"), element_id="murmur_port_post", value=voice_port, lang=l),
        _kv_row(label=_s(l, "voice.password"), element_id="murmur_password_post", value=voice_password, lang=l),
    ]

    return f"""
    <div class="stepcard">
      <h4>{h(_s(l, "voice.title"))}</h4>
      <div class="muted">{h(_s(l, "voice.subtitle"))}</div>
      <div style="margin-top:12px;">
        <ol style="margin:0; padding-left:20px; line-height:1.7;">
          <li>{steps[0]}</li>
          <li>{steps[1]}</li>
          <li>{steps[2]}</li>
          <li>{steps[3]}</li>
        </ol>
      </div>
      <div style="margin-top:14px; line-height:1.8;">
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
    l = lang_norm(lang)
    return f"""
    <div class="guidegrid">
      {_voice_setup_block(lang=l, base=base, token=token, bump=bump)}
      {_placeholder_card(_s(l, "maps.title"), _s(l, "maps.body"))}
      {_placeholder_card(_s(l, "addons.title"), _s(l, "addons.body"))}
    </div>
    """
