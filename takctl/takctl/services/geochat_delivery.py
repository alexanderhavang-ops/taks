"""Verify a voice-package destination, without authenticating GeoChat payloads.

TAK Server's active TLS subscription binds the destination UID to its account.
The chat message itself is not an authenticated account assertion. This context
therefore permits only delivery back to that exact device, never private reads.
"""
import re


def voice_delivery_principal(sender_uid):
    if not isinstance(sender_uid, str) or not sender_uid or len(sender_uid) > 256:
        raise PermissionError('A connected TAK device is required')
    from takctl.services.marti_api import marti_json
    from takctl.services.business_access import account_actor
    from takctl.onboarding.selection import load_selection
    from takctl.onboarding.voice_topology import derive_voice_topology

    payload = marti_json('/Marti/api/subscriptions/all')
    rows = payload.get('data') if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise PermissionError('TAK device verification unavailable')
    matches = [row for row in rows if isinstance(row, dict) and row.get('clientUid') == sender_uid]
    if len(matches) != 1:
        raise PermissionError('TAK device is disconnected or ambiguous')
    session = matches[0]
    username = session.get('username')
    if (session.get('protocol') not in ('tls', 'quic') or not isinstance(username, str)
            or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}', username)):
        raise PermissionError('An authenticated TAK connection is required')
    account = account_actor(username, transport='geochat')
    selection = load_selection(username) or {}
    channels = selection.get('channels') or []
    if isinstance(channels, dict):
        channels = channels.get('available') or channels.get('default') or []
    if not isinstance(channels, list):
        channels = []
    names = [str(value.get('name') or '').strip() if isinstance(value, dict)
             else str(value).strip() for value in channels]
    if not any(names):
        names = derive_voice_topology(None, selection.get('ctx') or {}).get('seed_channels') or []
    names = tuple(dict.fromkeys(name for name in names if isinstance(name, str) and name.strip()))
    callsign = session.get('callsign') or username
    if not isinstance(callsign, str) or not re.fullmatch(r'\w[\w .-]{0,63}', callsign):
        callsign = username
    return {**account, 'authenticated': False, 'admin': False,
            'delivery_verified': True, 'sender_uid': sender_uid,
            'callsign': callsign, 'device_uids': (sender_uid,), 'channels': names}
