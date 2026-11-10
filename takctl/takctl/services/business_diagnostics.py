"""Bounded operational diagnostics. No shell, deploy, arbitrary paths or writes."""
import json
from pathlib import Path
import re
import subprocess
import socket

DEVICE_FIELDS = ('client_uid', 'observed_callsign', 'state', 'last_cot_time', 'last_event_time',
                 'connection_event_name', 'tak_platform', 'tak_device', 'tak_version', 'tak_os',
                 'certs_n', 'revoked_certs_n')
LOGS = {'voice_auth':'taks-mumble-voice-pin-auth.log', 'openfire':'openfire/openfire.log',
        'takctl':'takctl-web.log', 'installer':'taks-installer-state.log',
        'business_tests':'taks-business-mcp-tests.log', 'nginx':'nginx/error.log'}


def own_account(actor, username):
    username = str(username or actor['username'])
    if not actor.get('authenticated') or (not actor.get('admin') and username != actor['username']):
        raise PermissionError('Account outside your scope')
    return username


def onboarding(actor, username=''):
    username = own_account(actor, username)
    from takctl.onboarding.service_builder import build_service
    from takctl.onboarding.onboarding_db import maybe_db
    db, error, _, _ = maybe_db()
    card = build_service().user_card(username=username, db=db, recent_minutes=120)
    header = card.get('header') or {}
    voice = (card.get('voice') or {}).get('user') or {}
    return {'username': username,
            'configured_callsign': header.get('configured_callsign') or header.get('callsign'),
            'observed_callsign': header.get('current_observed_callsign'),
            'onboarding_status': card.get('onboarding_status'),
            'devices': [{k:d.get(k) for k in DEVICE_FIELDS} for d in card.get('devices', [])],
            'voice_connected': bool(voice.get('connected_now')),
            'database_available': db is not None}


def enrich_actor(actor):
    from takctl.onboarding.selection import load_selection
    result = dict(actor)
    status = onboarding(actor)
    devices = status['devices']
    result['device_uids'] = tuple(d['client_uid'] for d in devices if d.get('client_uid'))
    primary = next((d for d in devices if d.get('state') == 'current'), devices[0] if devices else {})
    result['sender_uid'] = str(primary.get('client_uid') or '')
    result['callsign'] = str(primary.get('observed_callsign') or status.get('configured_callsign') or actor['username'])
    selection = load_selection(actor['username'])
    channels = selection.get('channels') or {}
    if isinstance(channels, dict):
        channels = channels.get('available') or channels.get('default') or []
    result['channels'] = tuple(str(v.get('name') or '') if isinstance(v,dict) else str(v) for v in channels)
    return result


def log_tail(actor, source, lines=40):
    if not actor.get('admin'):
        raise PermissionError('Raw logs require administrator access')
    if source not in LOGS or not isinstance(lines, int) or not 1 <= lines <= 100:
        raise ValueError('Unknown log source or invalid line limit')
    result = subprocess.run(['sudo','-n','/opt/tak/tools/takctl/bin/takctl-log-helper',
                             'read','/'+LOGS[source],'--mode','tail','--lines',str(lines)],
                            capture_output=True, text=True, timeout=10, check=False)
    if result.returncode:
        return {'ok':False, 'source':source, 'error':'Log unavailable'}
    data = json.loads(result.stdout)
    return {'ok':True, 'source':source, 'content':str(data.get('content') or '')[-12000:]}


def own_events(actor, username=''):
    # Only structured fields from rows already attributed to the authenticated
    # account. Never filter raw global logs by user-controlled callsign text.
    status = onboarding(actor, username)
    return {'username':status['username'], 'events':[
        {k:d.get(k) for k in ('client_uid','state','connection_event_name','last_event_time','last_cot_time')}
        for d in status['devices']]}


def file_metadata(actor, source):
    if not actor.get('admin') or source not in LOGS:
        raise PermissionError('File unavailable')
    path = Path('/var/log') / LOGS[source]
    if path.is_symlink():
        raise PermissionError('Symlinks are not exposed')
    stat = path.stat()
    return {'source':source, 'bytes':stat.st_size, 'modified':stat.st_mtime}


def product_health(actor):
    if not actor.get('admin'):
        raise PermissionError('Administrator required')
    listeners={}
    for name,port in {'cot':8089,'marti':8443,'enrollment':8446,'xmpp':5222,'voice':64738,'ldap':389,'postgres':5432}.items():
        try:
            with socket.create_connection(('127.0.0.1',port),timeout=0.5):
                listeners[name]=True
        except OSError:
            listeners[name]=False
    path=Path('/opt/tak/takctl-state/node-health.json')
    try: cached=json.loads(path.read_text())
    except (OSError,ValueError): cached={}
    return {'ok':True,'listeners':listeners,'checks':cached.get('checks',{}),'rollup':cached.get('rollup',{})}
