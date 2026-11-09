"""Authenticated service-native Business MCP operations; no arbitrary URLs or shell."""
import base64
import json
import logging
from pathlib import Path
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request

from takctl.config import load_config, load_secrets
from takctl.services.ldap_user_store import LdapUserStore

READS = {'ldap': {'users', 'user', 'groups'}, 'mumble': {'snapshot'},
         'openfire': {'sessions', 'rooms', 'room', 'occupants'}}
WRITES = {'ldap': {'group_create', 'group_delete', 'user_groups_set'},
          'mumble': {'channel_create', 'channel_rename', 'channel_delete'},
          'openfire': {'room_create', 'room_delete', 'room_subject_set'}}
NAME = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_. -]{0,79}$')


ARGUMENTS = {
    ('ldap', 'users'): {'limit'}, ('ldap', 'user'): {'username'}, ('ldap', 'groups'): {'username'},
    ('ldap', 'group_create'): {'group'}, ('ldap', 'group_delete'): {'group'},
    ('ldap', 'user_groups_set'): {'username', 'groups'},
    ('mumble', 'snapshot'): {'server_id'},
    ('mumble', 'channel_create'): {'server_id', 'name', 'parent'},
    ('mumble', 'channel_rename'): {'server_id', 'channel_id', 'name'},
    ('mumble', 'channel_delete'): {'server_id', 'channel_id'},
    ('openfire', 'sessions'): set(), ('openfire', 'rooms'): {'chat_service'},
    ('openfire', 'room'): {'chat_service', 'room'}, ('openfire', 'occupants'): {'chat_service', 'room'},
    ('openfire', 'room_create'): {'chat_service', 'room'}, ('openfire', 'room_delete'): {'chat_service', 'room'},
    ('openfire', 'room_subject_set'): {'chat_service', 'room', 'subject'},
}


def _name(args, key):
    value = args.get(key)
    if not isinstance(value, str) or not NAME.fullmatch(value) or value in ('.', '..'):
        raise ValueError('Invalid ' + key)
    return value


def _number(args, key, default=None, minimum=0):
    value = args.get(key, default)
    if type(value) is not int or value < minimum or value > 2**31 - 1:
        raise ValueError('Invalid ' + key)
    return value


def _redact(value):
    if isinstance(value, dict):
        return {k: ('[REDACTED]' if any(x in k.lower() for x in
            ('password', 'secret', 'token', 'authorization')) else _redact(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(v) for v in value]
    return value


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _openfire(method, path, payload=None):
    # Admin console is loopback-only. Basic authenticates against the same LDAP
    # admin account; no second Openfire password is introduced.
    cfg, sec = load_config(), load_secrets()
    username = str(cfg.get('takctl_admin_user', 'admin') or 'admin')
    password = str(sec.get('takctl_admin_password', '') or '')
    if not password:
        return {'ok': False, 'error': 'Installer admin credential unavailable'}
    auth = base64.b64encode((username + ':' + password).encode()).decode()
    request = urllib.request.Request('http://127.0.0.1:9090/plugins/restapi/v1' + path,
        method=method, data=None if payload is None else json.dumps(payload).encode(),
        headers={'Authorization': 'Basic ' + auth, 'Accept': 'application/json',
                 'Content-Type': 'application/json'})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        with opener.open(request, timeout=10) as response:
            body = response.read(1_048_577)
            if len(body) > 1_048_576:
                return {'ok': False, 'error': 'Response too large'}
            data = json.loads(body) if body else None
            return {'ok': True, 'http_status': response.status, 'data': data}
    except urllib.error.HTTPError as exc:
        return {'ok': False, 'http_status': exc.code, 'error': 'Openfire REST request rejected'}
    except (OSError, ValueError):
        return {'ok': False, 'error': 'Openfire REST API unavailable'}


def _ldap(operation, args):
    store = LdapUserStore()
    if operation == 'users':
        limit = _number(args, 'limit', 100, 1)
        if limit > 500:
            raise ValueError('limit exceeds 500')
        users = list(store.list_users())[:limit]
        return {'ok': True, 'users': [{'username': u.username, 'groups': list(u.groups or [])} for u in users]}
    if operation in ('user', 'groups'):
        username = _name(args, 'username')
        user = store.get_user(username)
        return {'ok': user is not None, 'username': username,
                'groups': list(store.groups_for_user(username)) if user else []}
    group = _name(args, 'group') if operation.startswith('group_') else None
    if operation == 'group_create':
        store.ensure_group(group)
        return {'ok': True, 'group': group}
    if operation == 'group_delete':
        if group == store.config.admin_group:
            raise ValueError('Administrator group cannot be deleted through this tool')
        store._ldapdelete(store.config.group_dn(group))
        return {'ok': True, 'group': group}
    if operation == 'user_groups_set':
        username = _name(args, 'username')
        groups = args.get('groups')
        if not isinstance(groups, list) or len(groups) > 100:
            raise ValueError('groups must be a list of at most 100 names')
        for group in groups:
            _name({'group': group}, 'group')
        if not store.get_user(username):
            return {'ok': False, 'error': 'LDAP user not found'}
        store.ensure_user(username, groups=groups)
        return {'ok': True, 'username': username, 'groups': store.groups_for_user(username)}
    raise ValueError('Unknown LDAP operation')


def _mumble(operation, args):
    clean = {'server_id': _number(args, 'server_id', 1, 1)}
    if operation in ('channel_create', 'channel_rename'):
        clean['name'] = _name(args, 'name')
    if operation == 'channel_create':
        clean['parent'] = _number(args, 'parent', 0)
    if operation in ('channel_rename', 'channel_delete'):
        clean['channel_id'] = _number(args, 'channel_id', minimum=1)
    worker = Path(__file__).with_name('mumble_ice_worker.py')
    result = subprocess.run(['/usr/bin/python3', '-I', str(worker)],
        input=json.dumps({'operation': operation, 'arguments': clean}),
        text=True, capture_output=True, timeout=15, check=False)
    if len(result.stdout) > 1_048_576:
        return {'ok': False, 'error': 'Response too large'}
    try:
        return _redact(json.loads(result.stdout))
    except ValueError:
        return {'ok': False, 'error': 'Mumble Ice API unavailable'}


def _openfire_operation(operation, args):
    service = _name({'service': args.get('chat_service', 'conference')}, 'service')
    query = '?servicename=' + urllib.parse.quote(service, safe='')
    if operation == 'sessions':
        return _openfire('GET', '/sessions')
    if operation == 'rooms':
        return _openfire('GET', '/chatrooms' + query)
    room = _name(args, 'room')
    path = '/chatrooms/' + urllib.parse.quote(room, safe='')
    if operation == 'room':
        return _openfire('GET', path + query)
    if operation == 'occupants':
        return _openfire('GET', path + '/occupants' + query)
    if operation == 'room_create':
        return _openfire('POST', '/chatrooms' + query, {
            'roomName': room, 'naturalName': room, 'description': room,
            'persistent': True, 'publicRoom': True})
    if operation == 'room_delete':
        return _openfire('DELETE', path + query)
    if operation == 'room_subject_set':
        subject = args.get('subject')
        if not isinstance(subject, str) or len(subject) > 500:
            raise ValueError('Invalid subject')
        existing = _openfire('GET', path + query)
        if not existing.get('ok'):
            return existing
        data = existing.get('data')
        if not isinstance(data, dict):
            return {'ok': False, 'error': 'Invalid Openfire room response'}
        data['subject'] = subject
        return _openfire('PUT', path + query, data)
    raise ValueError('Unknown Openfire operation')


def call(service, operation, arguments=None, *, write=False, confirm_write=False):
    definitions = WRITES if write else READS
    if not isinstance(service, str) or not isinstance(operation, str) or service not in definitions or operation not in definitions[service]:
        raise ValueError('Unsupported service operation')
    if not isinstance(arguments, dict):
        raise ValueError('arguments must be an object')
    if set(arguments) - ARGUMENTS[(service, operation)]:
        raise ValueError('Unknown service arguments')
    if write and confirm_write is not True:
        return {'ok': False, 'confirmation_required': True}
    try:
        result = {'ldap': _ldap, 'mumble': _mumble, 'openfire': _openfire_operation}[service](operation, arguments)
        logging.getLogger('takctl.business_mcp').info(
            'service_operation service=%s operation=%s write=%s ok=%s',
            service, operation, write, result.get('ok'))
        return _redact(result)
    except ValueError:
        raise
    except Exception as exc:
        return {'ok': False, 'error': type(exc).__name__, 'service': service}
