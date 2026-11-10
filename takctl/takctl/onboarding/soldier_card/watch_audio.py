from html import escape
from pathlib import Path

_SCRIPT = Path(__file__).with_suffix('.js').read_text(encoding='utf-8')


def watch_audio_block(*, base: str, token: str, lang: str) -> str:
    sv = lang == 'sv'
    title = 'Ställ in klockans röstapp med ljud' if sv else 'Set up watch voice by sound'
    help_text = ('Öppna WearTAK Voice på klockan och välj ”Listen for setup”. Håll telefonens högtalare nära klockan. Spela upp ljudet och godkänn servern på klockan. Ingen inmatning på klockan.' if sv else
                 'Open WearTAK Voice on the watch and tap “Listen for setup”. Hold the phone speaker near the watch. Play the sound, then accept the server on the watch. No typing on the watch.')
    labels = {
        'playing': 'Spelar… håll telefonen nära klockan.' if sv else 'Playing… keep the phone near the watch.',
        'finished': 'Godkänn inställningarna på klockan. Spela igen om inget hördes.' if sv else 'Accept setup on the watch. Replay if nothing was heard.',
        'stopped': 'Stoppad.' if sv else 'Stopped.',
        'failed': 'Kunde inte starta. Kontrollera anslutningen eller försök igen om en minut.' if sv else 'Could not start. Check the connection or retry in a minute.',
    }
    attributes = ' '.join(f'data-{key}="{escape(value, quote=True)}"' for key, value in labels.items())
    endpoint = escape(f'{base}/api/onboarding/cards/{token}/watch-voice/ticket', quote=True)
    note = ('Gör detta privat. Ljudet innehåller en engångslänk som gäller i tre minuter. Klockan behöver internet.' if sv else
            'Do this privately. The sound carries a single-use setup link valid for three minutes. The watch needs internet.')
    return f'''<section class="stepcard interactive-only" style="margin-top:14px;">
<h4>{title}</h4><div class="muted">{help_text}</div><div class="dlrow">
<button id="watch_audio_play" class="btn" data-endpoint="{endpoint}" {attributes}>{'Spela ljudkod' if sv else 'Play audio code'}</button>
<button id="watch_audio_stop" class="btn">{'Stoppa' if sv else 'Stop'}</button></div>
<details><summary>{"Återställ klockåtkomst" if sv else "Reset watch access"}</summary><button class="btn" id="watch_audio_reset" data-endpoint="{escape(f"{base}/api/onboarding/cards/{token}/watch-voice/revoke", quote=True)}" data-confirm="{"Återkalla alla klockinloggningar för detta konto? Anslutna sessioner avslutas inte direkt." if sv else "Revoke every watch login for this account? Existing connected sessions will remain until disconnected."}">{"Återkalla klockinloggningar" if sv else "Revoke watch logins"}</button></details>
<div id="watch_audio_status" class="meta" role="status" aria-live="polite"></div><p class="muted">{note}</p>
</section><script>{_SCRIPT}</script>'''
